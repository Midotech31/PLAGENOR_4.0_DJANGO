# Décisions techniques

*Designed by Prof. Merzoug Mohamed.*

Ce document consigne les écarts assumés par rapport au prompt maître, leur
raison et l'alternative retenue.

## DT-01 — Python 3.11 accepté en plus de 3.12

**Prompt :** Python 3.12. **Constat :** l'environnement de développement
fournit Python 3.11.15. **Décision :** le code n'utilise aucune fonctionnalité
postérieure à 3.11 (`StrEnum` est disponible depuis 3.11). L'application
fonctionne sur 3.11 comme sur 3.12 ; le guide d'installation recommande 3.12.
**Impact sécurité :** aucun.

## DT-02 — ReportLab plutôt que WeasyPrint

**Prompt :** ReportLab **ou** WeasyPrint. **Décision :** ReportLab. WeasyPrint
exige GTK/Pango sous Windows, ce qui alourdit l'installation locale sans
bénéfice pour un rapport structuré. ReportLab est une dépendance Python pure.
**Impact :** installation Windows plus simple et reproductible.

## DT-03 — OpenCV non requis

**Prompt :** « Pillow et OpenCV si disponible ». **Décision :** le
prétraitement OCR utilise Pillow seul (orientation EXIF, niveaux de gris,
contraste automatique, filtre médian). OpenCV ajoute ~60 Mo pour un gain
marginal sur des scans administratifs. Le pipeline reste identique et
documenté ; OpenCV pourra être ajouté sans changer l'interface.

## DT-04 — Agents déterministes, sans modèle génératif dans le chemin de décision

**Prompt V3 :** « agents IA spécialisés connectés à Internet », mais aussi
« n'intègre aucune IA générative dans le chemin de décision » et « zéro
affirmation orpheline de source ».

**Décision :** les six agents sont des analyseurs **déterministes et
explicables** opérant sur des sources publiques réellement consultées. Leur
raisonnement repose sur le palier de la source, le nombre de domaines
indépendants, les dates, les concordances et des seuils versionnés. Chaque
affirmation porte son URL, sa date de consultation, son type de source et son
niveau de preuve.

**Raison :** un modèle génératif ne peut pas garantir l'absence d'affirmation
orpheline de source ni la reproductibilité d'un résultat. Le contrat de
fiabilité (invariants 1, 2, 10, 11) prime sur le choix d'implémentation.

**Conséquence :** aucune hallucination n'est possible — un agent ne peut
énoncer que ce qu'une source consultée contient. Une assistance rédactionnelle
générative pourra être ajoutée ultérieurement, à condition d'être facultative,
isolée, clairement signalée et incapable de modifier un score, une conformité,
une alerte ou une conclusion.

## DT-05 — Fournisseurs de recherche publics et sans clé

**Décision :** les fournisseurs par défaut (OpenAlex, Crossref, ROR, ORCID)
sont des API publiques, sans clé, orientées identité académique et
publications. Ils correspondent aux paliers 2 et 3 de la hiérarchie des
sources. **Raison :** aucun secret à stocker, conditions d'utilisation claires,
aucune donnée personnelle transmise. Un fournisseur nécessitant une clé peut
être enregistré localement ; la clé est lue uniquement dans l'environnement.

## DT-06 — Rapport à dix-neuf sections

**Prompt :** dix-huit sections imposées. **Décision :** les dix-huit sections
sont produites dans l'ordre exact, suivies d'une dix-neuvième section portant
le titre imposé par la section 10 du prompt V3 : « Classement externe indicatif
assisté par IA — non décisionnel… ». **Raison :** le ranking doit figurer au
rapport sous ce titre précis sans altérer la numérotation officielle.

## DT-07 — Pièces sourcées et pièces complémentaires séparées

**Constat :** le canevas officiel (`SRC-DOSSIER-PIECES`) liste quatorze pièces ;
le prompt en énumère vingt. **Décision :** les quatorze pièces sourcées portent
leur source et leur page ; les pièces complémentaires portent explicitement
`source_ref = « À confirmer par le Professeur Merzoug Mohamed ou par la
commission »`. **Conséquence :** l'absence d'une pièce complémentaire ne peut
jamais être présentée comme une non-conformité.

## DT-08 — Métadonnées de recherche en clair

**Décision :** référence, intitulé, organisateur, statut, numéros de page et
empreintes restent en clair pour permettre filtrage et tri locaux. Tout le
contenu substantiel est chiffré. **Limite explicitement documentée** dans
`SECURITE.md` §4 et `LIMITES.md`.

## DT-09 — Similarité par contenance plutôt que par ratio global

**Constat :** comparer une affiliation courte à un titre long avec un ratio de
similarité global produit systématiquement un score faible, donc des faux
négatifs. **Décision :** `core/text.containment` mesure la proportion de mots
du terme court retrouvés dans le texte long. **Raison :** la métrique est
explicable et affichable telle quelle à l'évaluateur, conformément à l'exigence
« afficher les deux graphies et la métrique utilisée ».

## DT-10 — Extraction automatique volontairement conservatrice

**Décision :** l'extraction des informations structurées propose des champs et
la détection des pièces propose des statuts `DETECTEE`, mais **aucune valeur
n'est confirmée automatiquement**. Toute confirmation exige une action humaine
avec page et passage source. **Raison :** invariants 2 et 7 du contrat de
fiabilité — une détection de titre ne vaut jamais confirmation.

## DT-11 — Playwright non intégré

**Prompt :** tests de parcours Playwright. **Décision :** les parcours critiques
sont couverts de bout en bout par pytest (import → OCR → qualification → grille
→ conclusion → validation G7 → export DOCX/PDF vérifié) et par Vitest côté
interface (démarrage direct, absence d'écran de connexion, RTL, accessibilité).
**Raison :** Playwright impose le téléchargement d'un navigateur, contraire à
l'exigence d'installation locale reproductible et hors ligne. L'ajout reste
possible sur un poste disposant déjà d'un navigateur piloté.

## DT-12 — Le score et l'avis deviennent des propositions automatiques

**Prompt V4, §2 :** « les anciennes consignes qui interdisaient toute
proposition automatique de note ou d'avis sont remplacées par les présentes
consignes ». **Décision :** l'application propose désormais le score
scientifique sur 100 et l'avis technique, tous deux motivés et rattachés à
leurs preuves. La grille officielle saisie par l'évaluateur et la conclusion
humaine restent des objets distincts, jamais préremplis par le moteur.
**Raison :** répondre à la nouvelle consigne sans confondre proposition et
décision. Chaque écran et chaque page du rapport porte la mention « aide à la
décision, ne valant pas décision officielle ».

## DT-13 — Trois moteurs déterministes, aucun modèle dans le chemin de décision

**Décision :** `regulatory_engine`, `scientific_scoring` et `decision_engine`
sont des fonctions pures des faits extraits. La même entrée produit toujours la
même sortie, et chaque point ou statut est explicable ligne à ligne.
**Raison :** un avis technique doit être reproductible et contestable. Un
modèle génératif dans le chemin de décision rendrait le résultat
non reproductible et l'argumentation invérifiable. Le modèle externe, quand il
est configuré, sert à la lecture sémantique et à la recherche publique — jamais
à choisir un statut, une note ou un avis.

## DT-14 — Effectifs indéterminés plutôt que ramenés à zéro

**Décision :** lorsqu'aucune entrée d'un comité ou d'une liste d'intervenants ne
porte de pays identifiable, `facts_service` laisse l'effectif à `None` au lieu
de compter zéro étranger. Le critère devient alors `NV`.
**Raison :** compter zéro affirmerait que la manifestation n'a aucun
participant étranger, ce que le dossier ne dit pas. « Non vérifiable » est la
seule réponse exacte, et elle n'est ni une conformité, ni une non-conformité.

## DT-15 — Le worker d'analyse est un fil dédié, pas une file externe

**Prompt V4, §6 :** « un worker distinct du serveur HTTP », « ne pas utiliser
uniquement une tâche en mémoire ou `FastAPI BackgroundTasks` ». **Décision :**
le travail est une ligne de `analysis_jobs` protégée par un bail transactionnel
et un battement ; le worker tourne dans un fil dédié démarré au lancement, et
`job_service.work_once()` permet de l'exécuter depuis n'importe quel processus.
**Raison :** l'état vit en base, donc le travail survit à la perte du
processus, et un second worker — voire un processus séparé — peut reprendre un
bail expiré sans aucun changement de code. Ajouter Redis ou Celery
contredirait l'exigence d'installation locale hors ligne.

## DT-16 — Le nombre de pages du rapport est mesuré, jamais promis

**Prompt V4, §15 :** « idéalement 3 pages […] dépasser 3 pages seulement
lorsque les preuves ou alertes l'exigent. Ne jamais tronquer pour respecter un
nombre de pages. » **Décision :** la mise en page compacte resserre marges,
corps, interlignes et largeurs de colonnes, et le rapport annonce le nombre de
pages réellement rendu (`page_count`, mesuré sur le PDF produit). Sur un
dossier documenté, les trois sections imposées occupent les pages 1, 2 et 3,
avec un débord du registre de preuves.
**Raison :** les 26 constats, les 24 sous-notes et le registre de preuves sont
tous exigés par le prompt. Les faire tenir en trois pages imposerait de les
tronquer, ce que le même prompt interdit. La table des preuves est abrégée avec
son total affiché — la liste est écourtée, jamais un constat.

## DT-17 — OCR : plusieurs prétraitements essayés, le meilleur mesuré retenu

**Constat d'usage :** l'OCR restait faible sur les images peu nettes.
**Décision :** `run_ocr` corrige d'abord l'orientation via l'analyse `--psm 0`
de Tesseract, puis essaie jusqu'à cinq prétraitements — standard, contraste
fort, binarisation d'Otsu, agrandissement ×2, redressement — et retient le
passage dont la note de qualité est la meilleure. Cette note combine la
confiance moyenne et le volume de texte utile plafonné : la confiance seule
récompenserait trois mots très sûrs, le volume seul récompenserait du bruit.
La recherche s'arrête dès qu'un passage dépasse nettement le seuil de
confiance, pour ne pas payer cinq passages sur un document déjà net.

**Gains mesurés** sur des dégradations fabriquées (voir
`tests/test_ocr_robustness.py`) : flou gaussien fort, 71,8 % → 92,8 % ; basse
résolution, 30,4 % sur 25 caractères → 85,0 % sur 88 caractères.

**Ce qui n'est pas fait, et pourquoi :** aucune fusion entre variantes. Le texte
retenu provient toujours d'un seul passage, donc il reste cohérent et
reproductible ; recoller les meilleurs mots de plusieurs passages produirait
une page que le moteur n'a jamais lue telle quelle. Tout est implémenté avec
Pillow seul — Otsu est calculé sur l'histogramme, l'inclinaison par profil de
projection — pour ne pas ajouter OpenCV ou NumPy à une installation qui doit
rester légère et hors ligne. Les variantes essayées et leurs scores sont
affichés à l'évaluateur : il voit ce qui a été tenté, pas seulement le résultat.

## DT-18 — Le rapport harmonisé devient la mise en page par défaut

**Modèle fourni :** `Rapport uniforme — Arganier, Adrar 2027`. **Décision :**
`uniform_report` reproduit ses huit sections, son vocabulaire d'**orientation
technique transmise au ministère**, sa fiche contrôlée en six rubriques, sa
grille scientifique en cinq dimensions et sa matrice à cinq colonnes. C'est le
format par défaut (`layout=harmonise`) ; `compact` et `detaille` restent
disponibles.

**Trois écarts assumés par rapport au modèle, tous dans le sens de la
vérifiabilité :**

* les valeurs lues mais non encore confirmées portent un astérisque dans la
  fiche. Le modèle, rédigé par un humain, n'en avait pas besoin ; une sortie
  automatique doit distinguer ce qu'elle a lu de ce qu'un évaluateur a validé ;
* la section 6 ne liste que l'action attendue par critère. Le modèle y met des
  actions courtes ; y recopier le constat doublerait la longueur du rapport et
  ferait doublon avec la section 3 ;
* la section 8 nomme les versions du référentiel et de la grille appliquées,
  ainsi que l'empreinte SHA-256 de la pièce. Sans elles, un rapport n'est pas
  refaisable à l'identique.

**Ce que le format garantit et qui ne vient pas du modèle :** aucun numéro de
passeport n'est reproduit, la section 4.1 est explicitement informative, et le
nombre de pages est mesuré sur le fichier produit — trois pages atteintes sans
retirer aucun des vingt-six constats.

## DT-19 — Échelle d'escalade OCR, et aveu d'échec plutôt qu'invention

**Constat mesuré, pas supposé :** sur des pages franchement dégradées
(caractères de 10 px, flou combiné à une basse résolution), **Tesseract et
RapidOCR échouent tous les deux complètement** — 0 mot-clé retrouvé sur 7.
Empiler un second moteur classique ne suffit donc pas.

**Décision :** `ocr_engines` organise une échelle — texte natif, Tesseract
multi-variantes, RapidOCR, modèle de vision, transcription humaine — et retient
la meilleure lecture mesurée. Aucune fusion entre moteurs : recoller les
meilleurs mots de deux passages produirait une page que personne n'a lue.

**Le point critique n'est pas de lire davantage, c'est de ne jamais présenter
une lecture fausse comme fiable.** Un défaut réel a été trouvé en mesurant :
sur une page illisible, RapidOCR renvoyait un texte faux avec une confiance
élevée, et l'application le présentait comme sûr. La confiance d'un moteur
mesure sa propre certitude, pas sa justesse. Trois doutes indépendants
déclenchent désormais la relecture humaine, chacun suffisant :

* confiance en deçà du seuil ;
* moins de 40 caractères utiles extraits d'une page entière ;
* **désaccord entre deux moteurs** — deux lecteurs indépendants qui divergent
  constituent un doute, exactement comme pour la relecture des constats.

Une page qu'aucun barreau ne lit reste marquée `needs_ocr` : la déclarer traitée
masquerait le trou au lieu de le signaler.

**Confidentialité du barreau de vision.** L'expurgation est textuelle et **ne
peut rien voir dans une image**. Le seul garde-fou possible est donc la
classification : un bloc image sans sensibilité déclarée est refusé par le
fournisseur, et une page `RESTREINT` n'atteint jamais ce barreau. Ces deux
refus sont dans le code, pas dans la configuration.

**Ce qui reste non mesuré :** le gain réel du barreau de vision. Aucun appel à
un modèle n'a été effectué faute de clé, et je ne peux pas servir de référence
sur un texte que j'ai moi-même généré — je saurais déjà ce qu'il dit. Le gain
annoncé pour ce barreau repose sur une différence d'architecture (lecture
contextuelle contre classification de glyphes), pas sur une mesure faite ici.

## DT-20 — Un refus doit apprendre quoi corriger

**Constat d'usage :** l'évaluateur recevait « Requête refusée (422). » en rouge
à chaque tentative de qualification d'un critère, sans savoir quoi corriger.

**Cause :** aucun gestionnaire n'était enregistré pour `RequestValidationError`.
FastAPI renvoyait alors son format par défaut (`{"detail": [...]}`), que
l'interface — qui lit `error.message` — ne savait pas traduire. La contrainte
réelle (motivation d'au moins huit caractères) n'apparaissait nulle part.

**Décision :** un gestionnaire traduit chaque contrainte de schéma en phrase
utilisable, nommant le champ et la règle, dans la même enveloppe d'erreur que
le reste de l'application. En complément, l'interface annonce la règle **avant**
l'envoi et garde le bouton d'enregistrement désactivé tant qu'elle n'est pas
respectée : la contrainte se comprend au lieu de se subir.

**Portée :** cela corrige toutes les saisies motivées de l'application —
qualification d'un critère, correction d'une sous-note, avis retenu — puisque
toutes reposent sur la même exigence de justification.

## DT-21 — Le rapport se télécharge, il ne se cherche pas

**Constat d'usage :** le rapport était produit, puis il fallait le retrouver
dans une liste plus bas et cliquer un lien textuel discret. Deux boutons
« officiel » figuraient au même niveau que les boutons de brouillon alors qu'ils
sont refusés tant que la porte G7 n'est pas franchie.

**Décision :** deux boutons principaux — Word et PDF — déclenchent le
téléchargement immédiatement après la génération. L'export officiel est replié
dans un dépliant qui énonce ses trois conditions. Le fichier porte désormais la
référence du dossier, sa version et son état (`Rapport_MSI-2027-014_v3_brouillon.pdf`)
plutôt qu'un identifiant technique : un rapport doit pouvoir se classer.

## DT-22 — L'arabe se lit de droite à gauche, y compris dans le code

**Constat d'usage :** les pages scannées, « et surtout en arabe », n'étaient pas
détectées. La mesure a montré deux défauts distincts, tous deux invisibles tant
que je n'avais testé que du latin.

**Défaut 1 — ordre des mots inversé.** `_rebuild_text` triait les mots d'une
ligne par abscisse croissante. C'est correct pour le français ; c'est faux pour
l'arabe. « طلب تنظيم تظاهرة علمية دولية » ressortait « دولية علمية تظاهرة تنظيم
طلب ». Toute recherche de terme, toute extraction de champ et tout extrait de
preuve portant sur de l'arabe étaient donc erronés. Le tri suit désormais
l'écriture réellement présente sur la ligne, détectée par les plages Unicode
fortement directionnelles — un chiffre ou une ponctuation n'indique aucun sens
de lecture.

**Défaut 2 — lignes coupées sur un scan réduit.** La tolérance de regroupement
des mots en lignes était une constante de 12 pixels, alors que la hauteur du
texte varie avec la résolution du rendu. Elle est maintenant proportionnelle à
la hauteur médiane des mots, et compare les centres verticaux plutôt que les
sommets, ce qui tolère des hauteurs de caractères différentes sur une même ligne.

**Défaut 3 — arrêt trop précoce.** Une confiance élevée sur trois mots suffisait
à clore la recherche de variantes, et une ligne manquée restait manquée. Un
volume de texte dérisoire fait désormais poursuivre.

**Mesures après correction**, sur trois rendus arabes (`tests/test_ocr_arabic.py`) :
page nette 3/3 lignes exactes, scan flou 3/3, scan réduit à 55 % 3/3. Aucune
régression sur le latin.
