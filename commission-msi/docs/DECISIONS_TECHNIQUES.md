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

## DT-23 — Contrôle en ligne des profils : ce qu'il examine, et ce qu'il refuse

**Demande :** que l'application fouille en ligne les profils des intervenants et
des membres des comités scientifiques et d'organisation étrangers afin de
détecter « des origines, affiliations ou activités douteuses ou à risque pour
l'Algérie ».

**Ce qui a été construit.** `SovereigntyScreeningAgent` examine, pour chaque
sujet PERSONNE, INSTITUTION, PARTENAIRE, SPONSOR et FINANCEUR, les sources
publiques déjà collectées par la veille, et signale les **rattachements
institutionnels** et **activités professionnelles publiquement documentés** qui
touchent l'une des douze catégories de vigilance nationale du référentiel
(172 termes) : mentions du Maroc, intégrité territoriale, relations
diplomatiques, défense et sécurité, infrastructures critiques, cyber et
biosécurité à double usage, données génétiques et biométriques, ressources
biologiques, patrimoine et archives, financement et influence, souveraineté des
données. Le vocabulaire n'est pas réécrit dans l'agent : il est chargé depuis le
référentiel validé, de sorte qu'un ajout ou un retrait s'y répercute sans
modification de code.

**Deux garde-fous, qui ne sont pas de la prudence ajoutée.**

1. *Exigence de contexte institutionnel.* Un terme n'est retenu que s'il
   apparaît auprès d'un marqueur d'affiliation, de programme, de financement ou
   de partenariat. Sans cela, une citation bibliographique — « l'auteur cite des
   travaux conduits au Maroc » — ou une simple mention géographique deviendrait
   un signalement. Un test le verrouille.
2. *Deux sources indépendantes.* En deçà, l'élément reste `ALLEGATION_TIERS` et
   `A_VERIFIER`, jamais un fait.

**Ce qui n'a pas été construit, et pourquoi.** Le mot « origines » figure dans la
demande ; il n'a pas été implémenté. Aucune détection ne porte sur la
nationalité, l'origine ethnique, la religion, le lieu de naissance, la
consonance d'un nom ou une opinion supposée. Ce refus n'est pas une préférence
d'implémentation : il est écrit dans le référentiel de l'application — « aucune
déduction à partir de la nationalité, de l'origine ou d'une opinion supposée » —
et dans l'encadré de portée du modèle de rapport de la commission elle-même :
« une nationalité, une formation, une publication, une participation académique
ou un lien institutionnel antérieur ne constitue pas automatiquement une
non-conformité ». Les trois catégories identitaires du référentiel
(`IDENTITE_RELIGION_LANGUE`, `DISCRIMINATION_HAINE`, `MEMOIRE_NATIONALE`) sont
donc explicitement exclues du champ, et un test échoue si l'une d'elles y entre.

Ce refus n'ampute pas la demande : un rattachement à une institution d'un pays
donné, un financement, une participation à un programme sont exactement ce que
la commission a besoin de voir, et ils sont documentables. Une origine ne l'est
pas, et un rapport qui la retiendrait serait attaquable.

**Restitution.** Section 4.2 du rapport harmonisé, avec le nom de la personne,
l'élément relevé, le nombre de sources indépendantes et le niveau de preuve.
L'absence de veille exécutée est écrite comme telle et n'est jamais présentée
comme une absence de risque. L'encadré de portée qui clôt la section 4 énumère
les critères refusés : sans cet énoncé, un lecteur prêterait à l'application un
profilage qu'elle n'exerce pas.

**Un nom d'agent distinct.** `AGENT_SOUVERAINETE_NATIONALE` a été ajouté plutôt
que de réutiliser `AGENT_INTEGRITE_PUBLIQUE` : deux agents partageant un nom
rendent leurs constats indiscernables dans le registre des affirmations.

## DT-24 — Le rapport final fait partie du travail, pas d'une seconde action

**Demande :** « un seul clic sur traiter le dossier devrait lancer le job pour
générer toutes les informations nécessaires y compris le rapport final ».

**Constat.** Le pipeline s'arrêtait au contrôle qualité. `REPORT_BUILDING`
portait un nom trompeur : il produisait l'**avis proposé**, pas le fichier. Le
rapport restait une action manuelle distincte, dans un autre onglet, avec un
choix de mise en page à faire — alors que la mise en page attendue est toujours
la même, celle du modèle de la commission.

**Étape ajoutée.** `REPORT_RENDERING`, à 99 % de progression, après
`REPORT_QA`. Elle produit le rapport harmonisé en Word **et** en PDF. Les deux
formats parce qu'ils ne servent pas au même usage : le Word s'annote et se
corrige, le PDF se transmet et se compte en pages.

**L'ordre n'est pas arbitraire.** Le rendu vient après le contrôle qualité, et
non l'inverse. Un contrôle bloquant qui échoue fait échouer le travail avant le
rendu : **aucun fichier n'est écrit pour un rapport partiellement valide**. Un
test le vérifie en faisant échouer le contrôle et en constatant que la liste des
rapports reste vide.

**Ce que l'étape ne fait pas.** Elle produit un **brouillon filigrané**.
L'export officiel reste un acte humain distinct, soumis à la porte
`G7_VALIDATION_HUMAINE`. L'application rédige le document ; elle ne le valide
pas à la place de l'évaluateur, et cette limite est écrite dans l'interface.

**Nombre de pages.** Mesuré sur le PDF réellement écrit, jamais estimé, et
conservé dans le point de reprise de l'étape.

**Interface.** Une carte « Rapport harmonisé produit » apparaît à la fin du
traitement, avec les liens de téléchargement directs. Elle n'offre aucun bouton
« générer » : le fichier existe déjà. Si la liste est vide, elle dit pourquoi —
un contrôle bloquant a échoué — plutôt que de laisser un blanc.

**Conformité aux modèles fournis.** Les cinq rapports uniformes de la commission
(Arganier/Adrar, Bouamama/Mostaganem, Chirurgie pédiatrique/Tlemcen,
SPRGM/USTO, SAHARA-SMART/ESASA) partagent la même ossature : sept sections
numérotées, l'encadré d'orientation en tête, une fiche à six rubriques, un
tableau d'appréciation 7×4 (cinq dimensions, un en-tête, un total) et la matrice
27×5 des 26 critères. Un test ouvre le fichier produit par le travail et vérifie
cette ossature.

**Un écart assumé.** Les libellés des six rubriques de la fiche varient d'un
modèle à l'autre — *Objet / Effectifs / Comité / Partenaires / Budget /
Publication* ici, *Nature / Programme clinique / Participants / Comité / Budget
/ Données* là. Un rédacteur humain les choisit selon ce que le dossier a de
saillant. L'application garde les six libellés du modèle Arganier plutôt que
d'inventer une heuristique de sélection : mieux vaut un intitulé stable et exact
qu'un intitulé deviné.

## DT-25 — Un défaut d'installation ne s'impute pas au document

**Constat d'usage :** une page arabe **parfaitement nette** — en-tête de la
République algérienne, cachet, signature — ressortait « Contenu illisible ou
insuffisamment fiable ». L'écriture était claire ; le message était faux.

**Mesure.** Sur un rendu arabe propre, les deux moteurs locaux ont été
comparés :

| Moteur | Résultat |
|---|---|
| Tesseract + paquet `ara` | 3 lignes sur 3, confiance 89 % |
| RapidOCR | `« rmg »`, confiance **62 %** |

**RapidOCR ne lit pas l'arabe.** Ses modèles PP-OCR embarqués couvrent le latin
et le chinois. Ce n'est pas une faiblesse de reconnaissance : c'est une absence
de couverture d'écriture, et elle n'était déclarée nulle part.

**Le mécanisme du message trompeur.** RapidOCR se déclare `available=True` et ne
lève aucune erreur. Il comptait donc comme « un moteur disponible », ce qui
désactivait le seul message honnête existant (« aucun moteur de lecture n'est
disponible »). Pire, ses trois caractères de bruit suffisaient à sortir du
chemin « aucun texte lu » : l'application affichait « moins de 40 caractères
utiles extraits d'une page entière » — vrai, mais qui fait porter le soupçon sur
la page. L'évaluateur retouche alors un scan déjà net, pour un manque qui
s'installe en dix minutes.

C'est exactement la faute corrigée en DT-19 sur le contrôle qualité : affirmer
un constat que l'on n'a pas les moyens d'établir. Ici l'application n'avait pas
les moyens de lire cette écriture, et elle a conclu que l'écriture était
mauvaise.

**Corrections.**

1. **Table `ENGINE_SCRIPTS`** : chaque barreau déclare les écritures qu'il sait
   lire. RapidOCR y figure comme latin seulement.
2. **`arabic_capable()`** distingue trois situations qui n'ont pas le même
   remède : Tesseract absent, Tesseract présent sans `ara`, mode `LOCAL_ONLY`
   sans barreau de vision. Le message nomme l'installation manquante, jamais une
   fatalité — et **ne propose jamais RapidOCR** comme remède, ce qui enverrait
   l'évaluateur dans un mur.
3. **Le complément d'explication est ajouté dès qu'aucun texte exploitable n'est
   lu**, pas seulement quand le texte est vide : c'est le cas `« rmg »` qui l'a
   imposé.
4. **`GET /api/v1/diagnostic-ocr`** et un bloc dépliant dans l'onglet
   « Document » : l'évaluateur voit quels moteurs sont présents, quelles langues
   Tesseract connaît, et si l'arabe est lisible — sans ouvrir un terminal.
5. **`install_windows.bat` vérifie le paquet `ara`**, et non plus la seule
   présence de `tesseract.exe`. Il donne le lien de `ara.traineddata` et
   rappelle que RapidOCR ne comble pas ce manque.

**Sur la lecture en ligne.** Le barreau de vision existe déjà et lit les pages
qu'aucun moteur local ne sait traiter, quelle que soit l'écriture. Il exige
`ANALYSIS_MODE=HYBRID_STRICT`, une clé fournie par l'environnement et
`ALLOW_EXTERNAL_AI=true`. Deux refus y restent inconditionnels et vérifiés dans
le code, pas seulement en configuration : une page classée restreinte n'est
jamais transmise, et aucune pièce d'identité ni aucun numéro de passeport ne
sort du poste. Ce barreau est un complément aux moteurs locaux, pas un
substitut : installer le paquet `ara` reste la première chose à faire, elle est
gratuite, hors ligne, et suffit dans la grande majorité des cas.

## DT-26 — « Installation terminée » ne veut rien dire si rien ne peut être lu

**Constat d'usage :** le journal d'installation d'un poste réel se termine sur
« === Installation terminee === » alors que **aucune page scannée ne pouvait y
être lue**. Deux échecs s'y étaient produits, tous deux ravalés au rang
d'avertissement.

**Échec 1 — la limite des 260 caractères de Windows.** L'installation de
RapidOCR s'est interrompue sur :

```
OSError: [Errno 2] No such file or directory:
'E:\...\backend\.venv\Lib\site-packages\onnxruntime\tools\ort_format_model\
 ort_flatbuffers_py\fbs\DeprecatedNodeIndexAndKernelDefHash.py'
```

Mesuré : ce chemin fait **262 caractères**, deux de trop. Le dossier
d'installation en occupait 133, et la dépendance la plus profonde en ajoute 129.
Ce n'est ni un problème de réseau ni un paquet cassé, et rien dans le message ne
le disait.

Le budget retenu — **101 caractères** pour le dossier d'installation — se déduit
de cette mesure : 260 moins les 129 observés, moins 30 de marge pour des
dépendances plus profondes. Un test le fige en vérifiant qu'il refuse bien le
chemin de 133 caractères qui a réellement échoué.

Le contrôle est fait **avant** toute installation. Échouer après plusieurs
minutes de téléchargement, sur un obstacle connu d'avance, n'est pas acceptable.
Deux remèdes sont proposés, l'un ou l'autre suffisant : déplacer le dossier vers
un chemin court, ou activer `LongPathsEnabled`.

**Échec 2 — Tesseract absent.** L'avertissement existait, mais il se perdait
entre deux pages de journal, et l'installation se déclarait terminée.

**Correction de fond.** `scripts/verify_install.py` répond à la seule question
qui compte : *cette installation lit-elle quelque chose, et quoi ?* Il
n'inventorie pas des paquets — il **fait lire deux images de contrôle**, une
latine et une arabe, et rapporte ce qui en sort. Trois verdicts distincts, parce
qu'ils n'appellent pas la même action :

| Verdict | Sortie | Signification |
|---|---|---|
| latin **et** arabe lus | 0 | rien ne manque |
| latin lu, arabe non | 1 | un dossier algérien sera à moitié illisible |
| rien n'est lu | 1 | toute page scannée restera vide |

L'installateur l'exécute et rappelle son résultat après le message de fin. Le
script est relançable à tout moment, sans réinstaller.

**Ce que l'échec de RapidOCR ne cause pas.** Il ne rend pas les pages arabes
illisibles : RapidOCR ne les lit pas de toute façon (DT-25). Le message
d'échec le dit désormais, pour éviter que l'évaluateur ne s'acharne sur la
mauvaise cause.

## DT-27 — Trouver Tesseract même lorsqu'il n'est pas dans le PATH

**Anticipation d'un échec certain.** Le diagnostic de DT-25 fonctionne : sur le
poste de l'évaluateur, le bandeau affiche « arabe NON lisible » et les trois
moteurs absents. L'action indiquée est d'installer Tesseract. Or l'installateur
Windows le plus répandu — celui d'UB-Mannheim, celui que la documentation
recommande — **n'ajoute pas Tesseract au PATH par défaut**. La case existe, elle
est facile à manquer, et rien ne le signale ensuite.

L'évaluateur aurait donc installé Tesseract, relancé l'application, et lu de
nouveau « tesseract absent ». Diagnostic faux, deuxième fois, et cette fois avec
le moteur bel et bien présent sur le disque.

`tesseract_command()` cherche désormais, dans cet ordre :

1. le chemin explicitement configuré (`MSI_TESSERACT_CMD`) — il prime toujours,
   c'est le seul moyen d'imposer une version précise ;
2. le PATH ;
3. les emplacements d'installation standard, y compris ceux d'une installation
   faite sans droits administrateur sous `%LOCALAPPDATA%`.

Trois appels système, et une impasse supprimée.

**Un défaut de portabilité trouvé par le test.** Les chemins utilisateur étaient
d'abord écrits `r"Programs\Tesseract-OCR\tesseract.exe"`. Hors de Windows,
l'antislash n'est pas un séparateur : le chemin composé devenait un nom de
fichier unique, et la recherche ne trouvait rien. Les emplacements sont
maintenant décomposés en segments. Le test l'a révélé parce qu'il s'exécute sur
Linux — un test qui n'aurait tourné que sous Windows aurait laissé passer la
faute.

## DT-28 — Sept sections, pas huit : conformité aux douze rapports de la commission

**Source.** Douze rapports « réexaminés » du CRU Ouest, fournis par la
commission. Analysés un à un, ils partagent une ossature stricte et deux
variantes conditionnelles.

**Ce que la mesure a montré.** Les douze rapports ont **sept sections**, jamais
huit. Aucun ne porte de section « Sources et traçabilité », de tableau des
règles de décision, ni de sous-section de contrôle en ligne. Le rapport produit
en portait les trois.

**Deux variations conditionnelles, et elles sont déterministes.** Le titre de la
section 6 suit l'orientation, sans exception sur les douze :

| Orientation | Titre de la section 6 |
|---|---|
| avis favorable, ou favorable sous réserves | Réserves maintenues et conditions préalables à la tenue |
| ajournement, quelle qu'en soit la forme | Compléments indispensables avant appréciation ministérielle |

Ce n'est pas une nuance de style : sous réserves, la manifestation peut se tenir
et les points listés sont des conditions préalables ; en ajournement, elle ne le
peut pas et les mêmes points sont des compléments à produire avant tout examen.

La section 4.1 n'apparaît que si les pièces portent des éléments à signaler, et
son titre suit ce qui est trouvé — « éléments relatifs au Maroc », ou « au Maroc
et à Israël ».

**Autres écarts corrigés**, tous mesurés sur les modèles : fiche de six lignes
sans ligne de titre ; légende de la matrice **avant** le tableau et non après ;
en-tête dans l'ordre intitulé, lieu et dates, pièce évaluée ; libellés de
dimensions `Faisabilité / gouvernance` et `Valorisation / suivi` ; suppression
des étiquettes `[FAIT EXTRAIT]` et `[CALCUL]` accolées aux paragraphes.

**Ce qui a été conservé, et pourquoi.** La provenance — référence, évaluateur,
date, version — ne figure dans aucun modèle. Elle descend en **pied de page**
plutôt que de disparaître : un document officiel sans référence ni date n'est
pas défendable, et le pied concilie la conformité du corps avec l'exigence de
traçabilité.

**Où sont passés les éléments retirés.** Dans l'interface, via
`GET /dossiers/{id}/rapport-details` et une carte « Traçabilité du rapport » :
sources, fondements réglementaires, versions, nombre de preuves citables,
contrôle en ligne des profils avec sa portée, contradictions connues, légendes
et principe probatoire. Rien n'est perdu ; ces éléments fondent le rapport et
doivent rester vérifiables, mais aucun des douze modèles ne les imprime et la
pièce transmise au ministère n'a pas à s'en alourdir.

Un détail d'écran mérite d'être noté : la carte ne répète ni les règles de
décision ni les versions de référentiel, déjà portées par les cartes d'avis et
de score. Deux listes identiques dans le même écran font douter qu'il s'agisse
bien des mêmes.

## DT-29 — Poser le paquet arabe plutôt que répéter la consigne

**Constat.** Après deux échanges et deux tentatives, le panneau de diagnostic du
poste affiche toujours « tesseract absent » et « arabe NON lisible ». La
consigne était juste et précise ; elle n'a pas suffi. L'installateur Windows de
Tesseract cache l'arabe derrière une case à cocher — « Additional language
data » — qu'il faut déplier, et que personne ne déplie.

Répéter une troisième fois n'aurait rien changé. `scripts/installer_arabe.py`
fait le travail : quand Tesseract est présent sans son modèle arabe, il pose le
paquet lui-même.

**Trois points de conception méritent d'être notés.**

1. **Le dossier `tessdata` est lu, pas deviné.** Il est extrait de la première
   ligne de `tesseract --list-langs`, qui nomme le dossier réellement utilisé.
   Le déduire du chemin du binaire serait faux dès qu'un `TESSDATA_PREFIX` est
   défini — et c'est fréquent sur un poste d'entreprise.

2. **Plusieurs adresses, sur des hôtes différents.** La forme
   `github.com/.../raw/...` a été **mesurée renvoyant 403** derrière le
   mandataire de cet environnement, là où `raw.githubusercontent.com` passe. Un
   poste administratif est exactement le genre d'endroit où l'un marche et
   l'autre non. Une seule adresse aurait été un point de rupture unique. Un test
   vérifie que les adresses ne partagent pas toutes le même hôte.

3. **Le résultat est vérifié sur le comportement, jamais sur le fichier.** Après
   écriture, le script redemande à Tesseract ce qu'il sait lire, puis fait lire
   une page arabe de contrôle. Un fichier déposé ne prouve rien : il peut être
   tronqué, ou posé dans un dossier que le moteur n'utilise pas. Un contrôle de
   taille écarte par ailleurs les pages d'erreur — 378 octets de HTML au lieu de
   1,4 Mo de modèle.

**Vérifié en conditions réelles**, et pas seulement en simulation : le paquet
arabe a été retiré du poste, le script relancé, et l'arabe est redevenu lisible —
téléchargement, écriture, confirmation par Tesseract et lecture d'une page arabe
de contrôle.

**Ce que le script ne fait pas.** Installer Tesseract lui-même. Poser un binaire
sur un poste administratif sans que son porteur le sache serait déplacé ; le
script cherche `winget`, propose la recherche du paquet, et n'écrit aucun
identifiant en dur — celui-ci change avec le dépôt, et une commande fausse
ferait perdre plus de temps qu'une recherche.

## DT-30 — Une commande relative n'est pas une instruction utilisable

**Constat d'usage.** La consigne donnée était
`backend\.venv\Scripts\python.exe scripts\installer_arabe.py`. Exécutée depuis
`C:\Users\dell`, elle a produit :

```
Le chemin d'accès spécifié est introuvable.
```

Le script n'a jamais démarré : `cmd.exe` échoue avant Python, et le message ne
nomme ni ce qui manque, ni le dossier attendu. Aucune amélioration du script
n'aurait pu rattraper cela — la faute était dans l'instruction, pas dans le code.

**Correction.** `reparer_ocr_arabe.bat`, à la racine, **double-cliquable**. Il
fait `cd /d "%~dp0"` avant toute chose, comme `install_windows.bat` et
`run_windows.bat` le faisaient déjà. Il vérifie que l'environnement virtuel
existe et, sinon, explique que le fichier doit rester à la racine du dossier de
l'application. Il se termine par `pause`, sans quoi la fenêtre se refermerait
avant d'être lue.

Un test vérifie ces trois points : la relocalisation, l'appel du script et la
pause. Un autre vérifie que le fichier entre bien dans l'archive de livraison —
un outil de dépannage absent de l'archive ne dépanne personne.

**Identifiant winget.** Il n'était volontairement pas écrit en dur, faute de
pouvoir le vérifier. `winget search tesseract` exécuté sur le poste a renvoyé
`UB-Mannheim.TesseractOCR 5.4.0.20240606`. L'identifiant est désormais inscrit,
avec la mention qu'il a été **relevé** et non supposé, et la commande de
recherche reste indiquée au cas où le dépôt changerait.

À noter : l'installation par winget prend les options par défaut, qui n'incluent
que l'anglais. Installer Tesseract par winget ne rend donc **pas** l'arabe
lisible — c'est exactement le cas que `installer_arabe.py` traite ensuite.
