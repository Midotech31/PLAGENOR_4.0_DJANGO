"""Échelle d'escalade OCR : plusieurs moteurs, le meilleur mesuré est retenu.

Le constat qui fonde ce module est mesuré, pas supposé : sur des pages
franchement dégradées — caractères de 10 px, flou combiné à une basse
résolution — **Tesseract et RapidOCR échouent tous les deux complètement**
(0 mot-clé retrouvé sur 7). Empiler un second moteur classique ne suffit donc
pas ; il faut une échelle qui monte jusqu'à une lecture par modèle de vision,
et qui s'arrête honnêtement quand plus rien ne marche.

Barreaux, du moins coûteux au plus coûteux :

1. **texte natif** du PDF — gratuit et parfait quand il existe ;
2. **Tesseract** avec ses cinq prétraitements (`ocr_service`) ;
3. **RapidOCR** (modèles PP-OCR en ONNX) — second avis local, sans GPU. Mesuré
   meilleur sur la basse résolution, moins bon sur le flou : on garde donc le
   meilleur des deux plutôt que d'en remplacer un ;
4. **modèle de vision** — seul barreau qui lit vraiment une page très dégradée,
   parce qu'il s'appuie sur le contexte et pas sur la forme des glyphes.
   Disponible uniquement en `HYBRID_STRICT`, **jamais** sur une pièce
   d'identité ni sur une page classée restreinte ;
5. **transcription humaine requise** — quand tout a échoué. L'application le
   dit et n'invente rien.

Aucune fusion entre moteurs : le texte retenu provient toujours d'un seul
passage, donc il reste cohérent et reproductible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings

#: Message porté par une page qu'aucun barreau n'a su lire.
HUMAN_TRANSCRIPTION_REQUIRED = (
    "Aucun moteur n'a pu lire cette page de façon exploitable. Transcription "
    "humaine obligatoire : l'application ne devine pas un contenu."
)

#: Catégories de données que le barreau vision ne reçoit jamais.
NEVER_SENT = ("pièce d'identité", "passeport", "page classée restreinte")

#: Écritures que chaque barreau sait lire.
#:
#: Cette table n'est pas décorative : **RapidOCR, tel qu'il est distribué, ne
#: lit pas l'arabe.** Ses modèles PP-OCR embarqués couvrent le latin et le
#: chinois ; sur une page arabe il renvoie une chaîne vide sans lever d'erreur.
#: Sans cette table, il compte comme « un moteur disponible », et l'application
#: conclut « contenu illisible » là où la cause réelle est qu'aucun moteur
#: installé ne connaît l'écriture de la page. Accuser le document d'un défaut
#: d'installation est exactement le genre de constat faux que le reste de
#: l'application s'interdit.
ENGINE_SCRIPTS: dict[str, frozenset[str]] = {
    "tesseract": frozenset({"latin", "arabe"}),  # selon les paquets installés
    "rapidocr": frozenset({"latin"}),
    "vision": frozenset({"latin", "arabe"}),
}

#: Code de langue Tesseract requis pour l'arabe.
ARABIC_LANGUAGE = "ara"


def arabic_capable() -> tuple[bool, list[str]]:
    """L'arabe est-il lisible sur ce poste, et sinon que manque-t-il ?

    Renvoie l'état et la liste des installations qui le rétabliraient, pour que
    le message affiché nomme une action et non une fatalité.
    """
    from app.services import ai_provider, ocr_service

    missing: list[str] = []

    if ocr_service.is_available():
        if ARABIC_LANGUAGE in ocr_service.installed_languages():
            return True, []
        missing.append(
            "le paquet de langue arabe de Tesseract (« ara ») : Tesseract est "
            "installé mais ne connaît pas l'arabe"
        )
    else:
        missing.append(
            "Tesseract avec ses paquets « ara », « fra » et « eng » : c'est le seul "
            "moteur local qui lise l'arabe"
        )

    provider = ai_provider.get_provider()
    if provider.mode == ai_provider.HYBRID_STRICT and provider.available():
        return True, []
    missing.append(
        "ou, à défaut, le mode HYBRID_STRICT avec sa clé, qui active la lecture "
        "par modèle de vision"
    )

    # RapidOCR ne figure pas dans les remèdes : il ne lit pas l'arabe.
    return False, missing


@dataclass
class EngineResult:
    """Sortie d'un barreau, avec de quoi la comparer aux autres."""

    engine: str
    text: str
    confidence: float | None
    quality: float
    detail: dict = field(default_factory=dict)
    available: bool = True
    note: str = ""


def _quality(confidence: float | None, text: str) -> float:
    """Note comparable entre moteurs : confiance et volume utile plafonné.

    Identique à celle utilisée entre les variantes de Tesseract, pour que les
    barreaux soient comparés sur la même échelle.
    """
    from app.core.text import useful_char_count

    if confidence is None:
        return 0.0
    volume = min(useful_char_count(text), 1200) / 1200
    return round(0.7 * (confidence / 100) + 0.3 * volume, 4)


# --------------------------------------------------------------------------
# Barreau 2 — Tesseract multi-variantes
# --------------------------------------------------------------------------


def tesseract_engine(png_bytes: bytes, *, languages: str | None = None, **_kwargs) -> EngineResult:
    from app.services import ocr_service

    if not ocr_service.is_available():
        return EngineResult(
            engine="tesseract",
            text="",
            confidence=None,
            quality=0.0,
            available=False,
            note="Moteur Tesseract local introuvable.",
        )
    result = ocr_service.run_ocr(png_bytes, languages=languages)
    return EngineResult(
        engine="tesseract",
        text=result.text,
        confidence=result.confidence,
        quality=_quality(result.confidence, result.text),
        detail={
            "variante_retenue": result.parameters.get("variante_retenue"),
            "variantes_essayees": result.parameters.get("variantes_essayees"),
            "rotation_osd": result.parameters.get("rotation_osd"),
        },
    )


# --------------------------------------------------------------------------
# Barreau 3 — RapidOCR (PP-OCR en ONNX, local, sans GPU)
# --------------------------------------------------------------------------

_rapid_engine = None
_rapid_failed = False


def rapidocr_available() -> bool:
    global _rapid_engine, _rapid_failed
    if _rapid_failed:
        return False
    if _rapid_engine is not None:
        return True
    try:
        from rapidocr_onnxruntime import RapidOCR

        _rapid_engine = RapidOCR()
        return True
    except Exception:  # noqa: BLE001 - moteur optionnel : son absence n'est pas une panne
        _rapid_failed = True
        return False


def rapidocr_engine(png_bytes: bytes, **_kwargs) -> EngineResult:
    if not rapidocr_available():
        return EngineResult(
            engine="rapidocr",
            text="",
            confidence=None,
            quality=0.0,
            available=False,
            note="RapidOCR n'est pas installé : second avis local indisponible. "
            "Installez « rapidocr-onnxruntime » pour l'activer (aucun GPU requis).",
        )
    try:
        raw, _elapsed = _rapid_engine(png_bytes)  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001 - un échec de moteur n'interrompt pas la chaîne
        return EngineResult(
            engine="rapidocr",
            text="",
            confidence=None,
            quality=0.0,
            available=False,
            note=f"RapidOCR n'a pas abouti ({type(exc).__name__}).",
        )
    if not raw:
        return EngineResult(engine="rapidocr", text="", confidence=0.0, quality=0.0)

    lines = [item[1] for item in raw]
    scores = [float(item[2]) for item in raw if len(item) > 2]
    text = "\n".join(lines)
    confidence = round(sum(scores) / len(scores) * 100, 2) if scores else None
    return EngineResult(
        engine="rapidocr",
        text=text,
        confidence=confidence,
        quality=_quality(confidence, text),
        detail={"lignes": len(lines)},
    )


# --------------------------------------------------------------------------
# Barreau 4 — lecture par modèle de vision
# --------------------------------------------------------------------------

VISION_INSTRUCTION = (
    "Transcris littéralement tout le texte lisible de cette page de document "
    "administratif. Conserve l'ordre de lecture et les retours à la ligne. "
    "N'invente rien : si une zone est illisible, écris [illisible] à sa place. "
    "Ne commente pas, ne résume pas, ne traduis pas."
)


def vision_engine(
    png_bytes: bytes,
    *,
    sensitivity: str = "ORDINAIRE",
    provider=None,
    **_kwargs,
) -> EngineResult:
    """Lecture contextuelle d'une page très dégradée.

    Deux refus sont inconditionnels et vérifiés ici, pas seulement en
    configuration : une page restreinte n'est jamais transmise, et le mode
    `LOCAL_ONLY` n'ouvre aucune sortie.
    """
    from app.services import ai_provider

    if sensitivity == "RESTREINT":
        return EngineResult(
            engine="vision",
            text="",
            confidence=None,
            quality=0.0,
            available=False,
            note="Page classée restreinte : elle n'est jamais transmise à un modèle. "
            "Sa lecture relève d'une transcription humaine sur le poste.",
        )

    provider = provider or ai_provider.get_provider()
    if provider.mode != ai_provider.HYBRID_STRICT or not provider.available():
        described = provider.describe()
        missing = ", ".join(described.get("missing") or []) or "mode LOCAL_ONLY actif"
        return EngineResult(
            engine="vision",
            text="",
            confidence=None,
            quality=0.0,
            available=False,
            note=f"Lecture par modèle indisponible : {missing}.",
        )

    request = ai_provider.AiRequest(
        role="OCR_VISION",
        instruction=VISION_INSTRUCTION,
        blocks=[{"kind": "image/png", "bytes": png_bytes, "sensitivity": sensitivity}],
    )
    try:
        response = provider.complete(request)
    except ai_provider.AiError as exc:
        return EngineResult(
            engine="vision",
            text="",
            confidence=None,
            quality=0.0,
            available=False,
            note=f"Lecture par modèle refusée ou échouée ({exc.code}).",
        )

    text = str(response.content.get("text", "")).strip()
    if not text:
        return EngineResult(engine="vision", text="", confidence=0.0, quality=0.0)

    # Un modèle ne fournit pas de confiance par caractère. La proportion de
    # zones qu'il déclare illisibles est le seul indicateur honnête dont on
    # dispose, et elle est présentée comme telle.
    illegible = text.count("[illisible]")
    words = max(len(text.split()), 1)
    confidence = round(max(0.0, 1 - illegible / words) * 100, 2)
    return EngineResult(
        engine="vision",
        text=text,
        confidence=confidence,
        quality=_quality(confidence, text),
        detail={
            "modele": response.model_id,
            "zones_illisibles_declarees": illegible,
            "confiance_estimee": "proportion de zones déclarées lisibles, "
            "non une confiance par caractère",
        },
    )


#: Barreaux essayés dans l'ordre. Le nom sert de clé dans les comptes rendus.
LADDER = (
    ("tesseract", tesseract_engine),
    ("rapidocr", rapidocr_engine),
    ("vision", vision_engine),
)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


#: En deçà de ce nombre de caractères utiles, une page pleine n'a pas été lue.
MIN_USEFUL_CHARS = 40

#: Accord minimal entre deux moteurs pour qu'une lecture soit tenue pour sûre.
#: Deux lecteurs indépendants qui divergent constituent un doute, pas un fait —
#: c'est la même règle que la relecture indépendante des constats.
MIN_CROSS_ENGINE_AGREEMENT = 0.45


@dataclass
class LadderOutcome:
    text: str
    confidence: float | None
    engine: str
    attempts: list[dict]
    human_transcription_required: bool
    notice: str
    agreement: float | None = None


def read_page(
    png_bytes: bytes,
    *,
    languages: str | None = None,
    sensitivity: str = "ORDINAIRE",
    provider=None,
) -> LadderOutcome:
    """Monte l'échelle jusqu'à obtenir une lecture exploitable.

    On s'arrête dès qu'un barreau dépasse nettement le seuil de confiance : les
    barreaux suivants coûtent du temps, et le dernier peut coûter un appel
    externe. Sinon on va au bout et on retient le meilleur résultat mesuré.
    """
    settings = get_settings()
    good_enough = settings.ocr_low_confidence + 10

    attempts: list[dict] = []
    results: list[EngineResult] = []
    best: EngineResult | None = None

    for name, engine in LADDER:
        result = engine(
            png_bytes, languages=languages, sensitivity=sensitivity, provider=provider
        )
        attempts.append(
            {
                "moteur": name,
                "disponible": result.available,
                "confiance": result.confidence,
                "caracteres": len(result.text.strip()),
                "note_qualite": result.quality,
                "remarque": result.note,
            }
        )
        if not result.available:
            continue
        if result.text.strip():
            results.append(result)
        if best is None or result.quality > best.quality:
            best = result
        # Même prudence entre barreaux qu'entre variantes : une confiance
        # élevée sur un texte dérisoire ne clôt pas la recherche.
        from app.core.text import useful_char_count

        if (
            result.confidence is not None
            and result.confidence >= good_enough
            and useful_char_count(result.text) >= MIN_USEFUL_CHARS
        ):
            break

    if best is None or not best.text.strip():
        return LadderOutcome(
            text="",
            confidence=None,
            engine="aucun",
            attempts=attempts,
            human_transcription_required=True,
            notice=HUMAN_TRANSCRIPTION_REQUIRED + _capability_hint(),
        )

    # Trois doutes distincts, chacun suffisant à exiger une relecture humaine.
    reasons: list[str] = []

    if best.confidence is None or best.confidence < settings.ocr_low_confidence:
        reasons.append("confiance du moteur en deçà du seuil")

    from app.core.text import similarity, useful_char_count

    unusable = useful_char_count(best.text) < MIN_USEFUL_CHARS
    if unusable:
        reasons.append(
            f"moins de {MIN_USEFUL_CHARS} caractères utiles extraits d'une page entière"
        )

    # La confiance d'un moteur mesure sa propre certitude, pas sa justesse : un
    # moteur peut être très sûr d'un texte faux. L'accord entre deux lecteurs
    # indépendants est le seul contrôle croisé disponible localement.
    agreement: float | None = None
    others = [item for item in results if item is not best]
    if others:
        agreement = max(similarity(best.text, item.text) for item in others)
        if agreement < MIN_CROSS_ENGINE_AGREEMENT:
            reasons.append(
                f"désaccord entre moteurs ({agreement:.0%} de similitude) : "
                "au moins l'une des deux lectures est fausse"
            )

    uncertain = bool(reasons)
    confidence_text = f"{best.confidence:.0f} %" if best.confidence is not None else "inconnue"
    return LadderOutcome(
        text=best.text,
        confidence=best.confidence,
        engine=best.engine,
        attempts=attempts,
        human_transcription_required=uncertain,
        agreement=agreement,
        notice=(
            f"Lecture retenue : {best.engine} (confiance {confidence_text}). "
            + (
                "Relecture humaine obligatoire avant toute exploitation — "
                + " ; ".join(reasons)
                + "."
                if uncertain
                else "Au-dessus des seuils de fiabilité, ce qui ne dispense pas d'un "
                "contrôle des noms, dates et montants."
            )
            + (_capability_hint() if unusable else "")
        ),
    )


def _capability_hint() -> str:
    """Rappelle l'installation manquante quand rien d'exploitable n'a été lu.

    Ce complément existe à cause d'un cas mesuré : sur une page arabe nette,
    RapidOCR renvoie « rmg » à 62 % de confiance. Trois caractères de bruit
    suffisent à faire sortir du chemin « aucun texte » et à produire le message
    « moins de 40 caractères utiles » — vrai, mais qui laisse croire que la page
    est en cause. Elle ne l'est pas : c'est le poste qui n'a aucun moteur
    capable de cette écriture, et cela se répare.
    """
    capable, missing = arabic_capable()
    if capable:
        return ""
    return (
        " Aucun moteur installé sur ce poste ne sait lire l'arabe : si cette page est "
        "en arabe, ce n'est pas elle qui est illisible. Il manque "
        + " ; ".join(missing)
        + ". RapidOCR ne comble pas ce manque, ses modèles couvrent le latin."
    )


def diagnostic() -> dict:
    """État des barreaux, affichable à l'évaluateur.

    Ce diagnostic existe parce qu'un poste peut refuser de lire une page
    parfaitement nette, et que la cause est alors une installation manquante,
    pas le document. L'évaluateur doit pouvoir le constater lui-même en une
    seconde, sans lire un journal ni ouvrir un terminal.
    """
    from app.services import ai_provider, ocr_service

    provider = ai_provider.get_provider()
    tesseract_ok = ocr_service.is_available()
    languages = ocr_service.installed_languages() if tesseract_ok else []
    vision_ok = provider.mode == ai_provider.HYBRID_STRICT and provider.available()
    capable, missing = arabic_capable()

    return {
        "barreaux": [
            {
                "moteur": "tesseract",
                "disponible": tesseract_ok,
                "langues": languages,
                "ecritures": sorted(
                    ENGINE_SCRIPTS["tesseract"]
                    if ARABIC_LANGUAGE in languages
                    else {"latin"}
                ),
                "portee": "cinq prétraitements locaux ; bon sur le flou et le bruit. "
                "Seul moteur local capable de lire l'arabe, et uniquement si son "
                "paquet « ara » est installé.",
            },
            {
                "moteur": "rapidocr",
                "disponible": rapidocr_available(),
                "langues": ["latin", "chinois"],
                "ecritures": sorted(ENGINE_SCRIPTS["rapidocr"]),
                "portee": "modèles PP-OCR en ONNX, local et sans GPU ; mesuré meilleur "
                "sur la basse résolution. Ne lit pas l'arabe : sur une page arabe il "
                "renvoie un texte vide sans signaler d'erreur.",
            },
            {
                "moteur": "vision",
                "disponible": vision_ok,
                "langues": ["toutes écritures"],
                "ecritures": sorted(ENGINE_SCRIPTS["vision"]),
                "portee": "lecture contextuelle des pages très dégradées ; jamais "
                "utilisée sur une pièce d'identité ni en mode LOCAL_ONLY",
            },
        ],
        "arabe_lisible": capable,
        "manque_pour_l_arabe": missing,
        "jamais_transmis": list(NEVER_SENT),
        "limite": "Une page qu'aucun barreau ne lit est signalée « transcription "
        "humaine obligatoire ». L'application n'invente jamais un contenu.",
    }
