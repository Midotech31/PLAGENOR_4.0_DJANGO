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

## DT-31 — Élévation automatique, français manquant, et un faux « échec » causé par la police système

**Trois défauts trouvés en suivant l'usage réel jusqu'au bout**, après que
l'installation du paquet arabe a échoué une première fois puis réussi.

### 1. Écrire dans « Program Files » exige l'administrateur

`winget install --id UB-Mannheim.TesseractOCR` installe Tesseract dans
`C:\Program Files\Tesseract-OCR\`. Y déposer `ara.traineddata` a produit :

```
[ECHEC] Écriture impossible ... [Errno 13] Permission denied
```

`reparer_ocr_arabe.bat` se relance désormais lui-même avec élévation
(`net session` pour détecter l'absence de droits, `Start-Process -Verb RunAs`
pour les redemander). Un marqueur passé en argument (`ELEVE`) évite de
redemander en boucle si l'élévation échoue ou est refusée ; dans ce cas, le
message renvoie explicitement au clic droit « Exécuter en tant
qu'administrateur », plutôt que de boucler silencieusement.

### 2. Le français manquait aussi, et rien ne le signalait

Une fois l'arabe posé, les langues installées étaient `ara, eng, osd` — **pas
`fra`**, alors que `MSI_OCR_LANGUAGES` vaut `fra+ara+eng` par défaut et que les
dossiers de la commission sont bilingues français/arabe. `winget` n'installe
que l'anglais et le module d'orientation ; ni l'arabe ni le français n'y
étaient inclus.

`installer_arabe.py` est généralisé : `REQUIRED_LANGUAGES = ("ara", "fra")`,
chacune installée et **reconfirmée séparément en interrogeant Tesseract**,
selon le même principe que pour l'arabe seul. Le nom du fichier et son
entrée dans les deux lanceurs (`install_windows.bat`,
`reparer_ocr_arabe.bat`) sont conservés pour ne rien casser ; son objet est
élargi dans la documentation du module.

### 3. Le contrôle de lecture a rendu un faux « ÉCHOUÉE »

Après l'installation réussie du paquet, confirmée par Tesseract lui-même
(`ara` listé), le contrôle de lecture d'une page arabe de synthèse a échoué :

```
[OK]    Paquet arabe « ara » : présent.
[ECHEC] Lecture d'une page arabe de contrôle : ÉCHOUÉE.
```

**Mesuré, pas supposé** : `_render` charge la première police qui **s'ouvre**,
sans jamais juger la qualité du rendu. Sur ce Linux de développement, une
police latine sans jointure arabe correcte (Liberation Sans) a produit, à
partir de la même image source, un texte comme
`« الالالالالالالا لالالالالالالالالا... »` — Tesseract l'a lu avec 66 % de
confiance. Une police totalement dépourvue de glyphes arabes (Liberation Mono)
a produit presque exclusivement des chiffres. **Dans les deux cas, aucune
erreur n'est levée : le rendu est simplement faux**, et le seul signe en est le
texte lu.

C'est très probablement ce qui s'est produit sur le poste réel avec
`arial.ttf` : le paquet arabe était installé, confirmé par Tesseract, et
pourtant notre propre image de contrôle a échoué à le prouver — un défaut du
test, pas de l'installation.

**Correction, en trois parties :**

1. `ARABIC_FONTS` essaie désormais `tahoma.ttf` et `segoeui.ttf` — les polices
   historiquement chargées de l'arabe sur Windows — avant `arial.ttf` et
   `times.ttf`.
2. `_best_arabic_reading` essaie chaque police et retient la première lecture
   **exacte** ; à défaut, la moins suspecte.
3. `_looks_garbled(texte)` détecte un rendu raté : moins de 8 lettres arabes
   dans le résultat, ou une même paire de lettres représentant plus de 35 %
   des paires lues. Calibré sur les deux échecs mesurés (0,11 sur un rendu
   correct, 0,50 sur le rendu Liberation Sans) — marge large entre le cas
   correct et les deux cas ratés.

`check_engines` renvoie désormais un triplet `(latin_ok, arabic_ok,
arabic_inconclusive)`. Quand le paquet est confirmé présent par Tesseract et
que seul le rendu de contrôle est suspect, le verdict — dans
`verify_install.py` comme dans `installer_arabe.py` — dit explicitement que ce
n'est **pas la même chose qu'un paquet manquant**, et renvoie tester avec un
document réel plutôt que de s'en tenir à cet indicateur. Confondre les deux
aurait renvoyé l'utilisateur chercher, une nouvelle fois, une cause
d'installation qui n'existe plus.

**Ce qui reste vrai sans ambiguïté** : quand Tesseract est absent, ou que son
paquet arabe est réellement absent, le verdict reste un échec franc — rien
dans cette correction n'atténue un cas où le manque est réel.

## DT-32 — Le contrôle comparait le texte brut, jamais normalisé

**Le même faux « ÉCHOUÉE » est réapparu une troisième fois**, sur le même
poste, après DT-31 : Tahoma et Segoe UI ajoutés, détection de rendu garbled en
place, paquet arabe confirmé par Tesseract — et pourtant :

```
[OK]    Paquet arabe « ara » : présent.
[ECHEC] Lecture d'une page arabe de contrôle : ÉCHOUÉE.
```

**La cause, trouvée en isolant le calcul lui-même** : `check_engines`
comparait le texte lu **brut** à la ligne attendue par inclusion littérale
(`line in outcome.text`), sans jamais appeler `app.core.text.normalize` — la
même normalisation que le reste de l'application utilise pour tout
rapprochement de texte arabe (elle replie déjà alif maksoura vers ya, les
formes de alif, les diacritiques). Une lecture OCR n'est jamais pixel-parfaite
: une variante de graphie usuelle suffisait à faire échouer une lecture par
ailleurs correcte, et le message affirmait « ÉCHOUÉE » à tort.

**Mesuré, avec la fonction déjà présente dans le projet** (`containment`,
utilisée ailleurs pour comparer une affiliation courte à un texte long) :

| Texte | Comparaison littérale | `containment` après normalisation |
|---|---|---|
| Lecture correcte (variante alif maksoura) | échoue | **1.0** |
| Rendu garbled (police sans jointure) | échoue | 0.0 |
| Rendu garbled (police sans glyphes) | échoue | 0.0 |

Marge large entre le cas correct et les deux cas ratés : `containment` sépare
proprement ce que la comparaison littérale confondait.

**Correction.** `_reading_score` remplace l'inclusion littérale par la
moyenne de `containment(ligne, texte)` sur les deux lignes attendues.
`GOOD_ARABIC_SCORE = 0.7` retient une lecture comme bonne. Sous ce seuil,
**le verdict est désormais gouverné par un seul fait, celui qu'on peut
vérifier sans ambiguïté** : si Tesseract confirme lui-même le paquet
`ara` (déjà affiché juste au-dessus dans le rapport), le résultat est
**toujours** « non concluant », jamais « ÉCHOUÉE » — quel que soit le
score, garbled ou non. Le score et le drapeau garbled ne servent plus qu'à
composer le message, jamais à décider du verdict. Un test le verrouille
directement : un score artificiellement bas avec le paquet confirmé présent
ne doit jamais produire la chaîne « ÉCHOUÉE ».

**Ce qui reste un échec franc** : Tesseract absent, ou son paquet arabe
réellement absent. Rien dans cette correction n'atténue ce cas.

**Une leçon pour la suite** : ce test synthétique a maintenant produit trois
diagnostics erronés successifs sur le même poste, chacun corrigé sans
résoudre le suivant (police, puis rendu garbled, puis comparaison littérale).
C'est pourquoi le verdict ne dépend plus, structurellement, que du fait que
Tesseract confirme ou non le paquet : plus aucune amélioration future de ce
test synthétique ne pourra reproduire ce genre de faux négatif, puisqu'il ne
peut plus, par construction, l'emporter sur ce fait.

## DT-33 — RapidOCR n'a pas de wheel pour Python 3.13

**Mesuré sur le même poste** : `pip install rapidocr-onnxruntime==1.4.4` sous
Python 3.13.2 énumère des dizaines de versions, toutes `Requires-Python
<3.13`. Au moment de l'écriture, **aucune version de RapidOCR ne prend en
charge Python 3.13**. Ni un chemin trop long, ni un problème réseau : une
incompatibilité de version, qui se résoudra quand RapidOCR publiera une roue
compatible, pas avant.

`install_windows.bat` distingue maintenant ce message (« Could not find a
version that satisfies ») de celui du chemin trop long, et le dit pour ce
qu'il est plutôt que de laisser l'utilisateur chercher un remède qui n'existe
pas encore. L'application continue de fonctionner avec Tesseract seul, qui
lit l'arabe — RapidOCR ne le fait de toute façon pas.

## DT-34 — `HYBRID_STRICT` était une façade : le mode n'avait aucun client

**Constat, dans le code :** `HybridStrictProvider._call` exigeait qu'on lui
injecte un client et levait `ExternalAiNotConfigured` sinon ; **aucune
implémentation de client n'existait dans le projet**. Le mode était donc
entièrement configurable — variables d'environnement, refus documentés, écran
d'état, tests — et n'a jamais pu émettre un seul appel. Le barreau de vision de
DT-19 était inatteignable pour la même raison.

`app/services/ai_client.py` comble ce manque : un POST vers l'API Messages,
écrit avec la bibliothèque standard. Ajouter une dépendance HTTP pour une seule
requête aurait élargi la surface d'installation, qui est déjà le point le plus
fragile de ce projet sous Windows (DT-25, DT-33).

Quatre choix méritent d'être écrits :

* **`temperature: 0`.** Sur une tâche de relevé, la variabilité ne produit que
  deux lectures différentes du même dossier, sans qu'on puisse dire laquelle
  est la bonne ;
* **la clé ne circule que dans l'en-tête**, lue depuis la configuration, qui la
  prend dans l'environnement. Elle n'apparaît ni dans le corps, ni dans un
  message d'erreur : `_safe_detail` ne recopie jamais le corps de la réponse
  d'erreur, qui peut renvoyer la requête en écho — le journaliser rendrait au
  journal ce que l'expurgation vient d'en retirer ;
* **les blocs `thinking` sont ignorés à la lecture.** La chaîne de pensée
  privée n'est ni conservée ni affichée ;
* **un modèle inconnu devient `LookupError`**, que le fournisseur traduit en
  `MODEL_UNAVAILABLE`. Une erreur de configuration ne doit pas ressembler à une
  panne réseau, et aucun repli silencieux vers un modèle plus faible n'a lieu.

## DT-35 — Une expression régulière ne lit pas une page de garde

**Mesure sur le dossier réel de 76 pages** (BOUAMAMA, décembre 2026) :
l'extraction déterministe a retrouvé **4 champs sur 29, dont 2 faux**
(`intitule` = l'en-tête arabe de l'université ; `date_debut` = la date du guide,
pas celle de la manifestation). La page 12 énonce pourtant en clair l'intitulé,
l'université, la faculté, le laboratoire, les dates et le format.

**Cause exacte :** `_extract_labelled` exige la forme `Libellé : valeur` sur une
seule ligne. Un dossier réel est fait de blocs de titre, de tableaux et de
prose. Ce n'est pas un seuil à ajuster : aucune expression régulière ne lit une
page de garde.

**Ce que la mesure a aussi réfuté :** j'avais présenté l'OCR comme le levier
indispensable. Le pipeline complet relancé avec un OCR fonctionnel (51 pages
océrisées, 859 s) a produit un résultat **identique** à celui obtenu avec l'OCR
cassé — 29/100, 8 NC / 8 NV / 9 PC / 1 C. L'OCR fournissait déjà le texte ; ce
qui manquait, c'était la lecture.

**Décision :** une étape `SEMANTIC_READING` (`ai_semantic_reading`) fait lire le
texte par le modèle, **en mode `HYBRID_STRICT` uniquement**. C'est ce que faisait
l'IA ayant rédigé le rapport Word de référence.

Ce qu'elle ne change pas :

* **le chemin de décision reste déterministe (DT-13).** Le modèle propose des
  *valeurs de champs*. Les statuts C/PC/NC/NV, le score et l'avis restent
  calculés par les moteurs, à partir de ces valeurs une fois qualifiées. Une
  clé hors de la liste des 29 champs est rejetée : le modèle ne peut pas glisser
  un avis dans le dossier par ce chemin ;
* **rien n'est confirmé.** Tout est écrit au statut `A_VERIFIER`, comme
  l'extraction déterministe ;
* **rien n'est cru sur parole.** Chaque proposition doit citer une page **et** un
  extrait ; l'extrait est relu sur le texte local (`containment ≥ 0.85`) et la
  proposition est rejetée s'il ne s'y trouve pas. C'est la seule protection
  honnête contre une valeur plausible mais inventée, et les rejets sont comptés
  et affichés plutôt que tus ;
* **rien de restreint ne sort.** Les pages d'un document `RESTREINT` sont
  écartées à la source, en plus du refus du fournisseur.

**Arbitrage entre les deux producteurs.** Deux sources proposent désormais des
valeurs. Sans règle, la dernière passée gagnait — y compris l'heuristique
« première ligne significative de la page 1 » (0,5), celle-là même qui avait
produit le faux intitulé, écrasant une lecture argumentée (0,75).
`extraction_service.may_overwrite` pose la règle dans les deux sens : une
proposition ne remplace qu'une proposition **moins sûre qu'elle**. Un libellé
explicite (0,85) l'emporte donc sur une lecture, et une lecture l'emporte sur un
motif structurel ou une heuristique de position. Ce que l'évaluateur a qualifié
n'est jamais touché.

**Une panne d'appel n'est pas absorbée.** L'exception remonte, le travail
devient reprenable au dernier point de reprise valide, et les appels déjà payés
ne sont pas refaits. Absorber l'échec produirait un rapport d'apparence normale,
bâti sur une lecture qui n'a pas eu lieu.

**Ce qui n'est pas mesuré, et doit être dit :** aucun appel réel n'a été émis.
Je n'ai pas de clé API. Le chemin est construit et couvert par 17 tests avec un
ouvreur HTTP factice — aucun test ne sort du poste — mais **le gain sur le
dossier réel reste à mesurer par vous**, avec votre clé. Ce que je peux affirmer
est structurel, pas empirique : la voie déterministe a été mesurée insuffisante
sur ce dossier, et celle-ci lit le texte au lieu d'y chercher une forme.

## DT-36 — Le client aurait été refusé par l'API dès le premier appel

**Constat, avant tout appel réel.** Le client écrit en DT-34 envoyait
`"temperature": 0`, avec une justification qui semblait solide : sur une tâche
de relevé, la variabilité ne produit que deux lectures différentes du même
dossier. Le raisonnement était juste ; **le paramètre est refusé**. Les modèles
récents rejettent `temperature`, `top_p` et `top_k` avec une erreur 400. L'appel
de contrôle de `activer_hybrid_strict.bat` aurait donc échoué à la première
tentative, sur un motif que rien dans le message n'aurait relié à sa cause.

Deux autres défauts du même appel, trouvés en vérifiant celui-là :

* **`max_tokens: 4096` était un plafond de troncature.** Sur ces modèles la
  réflexion est active par défaut et **se compte dans ce plafond**. Le
  raisonnement d'une lecture de 25 pages l'aurait consommé avant la réponse, et
  le JSON serait arrivé coupé au milieu d'un champ — c'est-à-dire illisible,
  donc entièrement perdu. Porté à 16000 ;
* **un refus n'était pas traité.** Un filtre de sécurité rend un refus avec un
  code HTTP 200 et un `content` vide : c'est une réponse valide, pas une panne.
  Le code lisait `content` sans vérifier et produisait « réponse vide du
  modèle » — un message qui décrit le symptôme et cache la cause.

Le repli automatique est désormais demandé pour les modèles qui l'acceptent :
si un filtre refuse une page à tort, l'API réessaie d'elle-même sur un modèle de
secours plutôt que de bloquer le dossier. Il n'est **pas** envoyé aux autres
modèles — le paramètre y ferait échouer la requête, ce qui remplacerait un
risque rare par une panne certaine.

**Ce que cet épisode dit du reste.** Ces trois défauts étaient dans du code
couvert par dix-sept tests verts. Aucun ne pouvait les voir : ils vérifiaient
que le client envoie bien ce que j'avais décidé d'envoyer, pas que l'API
l'accepte. Un ouvreur factice ne refuse rien. La leçon n'est pas qu'il fallait
appeler l'API pour de vrai — je n'ai pas de clé — mais que **la vérification
d'une intégration ne peut pas venir de mes propres suppositions** : elle doit
venir de la référence de l'API, relue au moment d'écrire. Les trois tests
ajoutés vérifient maintenant l'absence des paramètres refusés, le plafond, et le
traitement du refus.

## DT-37 — Demander un secret avant de vérifier que l'application peut tourner

**Mesuré sur le poste de l'évaluateur.** `activer_hybrid_strict.bat` a déroulé
tout son discours, fait choisir le modèle, **fait saisir la clé API**, l'a
enregistrée — puis a rendu ceci :

```
ModuleNotFoundError: No module named 'sqlalchemy'
```

Deux fautes distinctes dans le même écran.

**La première est l'ordre.** Le script demandait un secret avant de vérifier
que l'environnement était en état. Faire manipuler une clé API pour échouer
ensuite sur une dépendance absente, c'est faire prendre un risque sans
contrepartie. La vérification de l'environnement passe désormais **avant** tout
le reste, y compris avant la question d'activation : rien n'est demandé tant que
l'application ne peut pas fonctionner.

**La seconde est le message.** Une trace Python brute, sous un titre
« l'appel de contrôle a échoué » qui invite à relire « la clé, l'identifiant du
modèle, ou le réseau » — aucun des trois n'était en cause, et **aucun appel
n'avait été tenté**. Le message envoyait donc chercher la panne exactement là
où elle n'était pas. `verifier_ia.py` traduit maintenant un
`ModuleNotFoundError` en cause probable et en remède, et dit explicitement ce
qui n'est pas responsable.

**La cause réelle, mesurable dans la trace elle-même** : le chemin
d'installation faisait **145 caractères**, pour un budget de 101 (DT-25).
L'installateur l'avait signalé et proposé de s'arrêter ; l'évaluateur a choisi
de continuer, et l'installation des dépendances a échoué en cours de route sans
que rien ne le rappelle au moment où la conséquence est apparue. Le diagnostic
mesure donc à nouveau la longueur du chemin **au moment de l'échec**, et non
seulement au moment de l'installation — c'est là qu'elle est utile.

Il précise aussi que les réglages et la clé survivent au déplacement du
dossier : sans cette phrase, la réaction naturelle est de tout ressaisir.

## DT-38 — Le message nommait l'état terminal au lieu de l'étape qui a échoué

**Copie d'écran du poste de l'évaluateur, mode `HYBRID_STRICT` actif, 81 pages
océrisées :**

> L'étape « **Interrompu** » n'a pas abouti : l'appel au modèle n'a pas abouti.
> **Vérifiez le dossier importé**, puis utilisez « Reprendre ».

Trois défauts dans une seule phrase.

**« Interrompu » n'est pas une étape**, c'est le libellé de l'état `FAILED`. La
cause : le gestionnaire d'erreur écrasait `job.step_label` avec le libellé de
l'état terminal **avant** de construire le message, qui relisait ce même champ.
Le nom de l'étape réellement en cause — « Lecture sémantique assistée du
dossier » — était perdu une ligne trop tôt. Il est désormais retenu avant
l'écrasement.

**« Vérifiez le dossier importé » désigne le seul endroit où le problème
n'était pas.** Une clé refusée, un crédit absent ou un modèle inconnu ne se
corrigent pas en relisant un PDF. Les échecs de configuration reçoivent
maintenant une action qui leur correspond : la commande `verifier_ia.py
--appel`, qui nomme la cause exacte, et le rappel que `LOCAL_ONLY` reste
utilisable en attendant.

**« Tentative : 6/3 ».** Le compteur dépassait son propre plafond parce que
chaque reprise humaine consommait une tentative sans jamais rouvrir le budget.
Une reprise demandée par l'évaluateur remet donc le compteur à zéro : il mesure
les reprises automatiques après panne, pas les décisions humaines.

**Ce que l'épisode coûte, et pourquoi c'est le vrai sujet.** La cause réelle
était une clé d'un autre fournisseur (`sk-proj-…`, OpenAI) enregistrée à la
place d'une clé Anthropic (`sk-ant-…`). L'application disposait de
l'information — l'API répond `401 authentication_error` — et ne l'a pas
transmise. C'est le troisième diagnostic de cette série (DT-32, DT-37) où le
défaut n'est pas la panne mais le fait que l'application **savait et n'a pas
dit**.

## DT-39 — Le modèle local n'est pas un pis-aller, c'est la bonne réponse

**Constat.** L'évaluateur n'a pas de clé API et n'a pas vocation à en avoir une :
c'est une commission publique, le paiement par carte internationale est un
obstacle réel, et le budget d'un service n'a pas à financer un abonnement pour
lire des dossiers.

**Ce que la contrainte a révélé.** Toute cette application existe pour qu'un
dossier de commission ne quitte jamais le poste. Le mode `HYBRID_STRICT`
transmettait des extraits expurgés — un compromis assumé, entouré de garde-fous
(DT-34, DT-35). Un modèle installé **sur le poste** supprime le compromis :
rien ne sort, pas même un extrait, pas même vers un fournisseur de confiance.

Le mode `LOCAL_MODEL` est donc **le mode recommandé**, et `HYBRID_STRICT`
devient l'option pour qui veut la meilleure lecture et accepte de transmettre.

**Pourquoi un petit modèle est utilisable ici alors qu'il ne le serait pas
ailleurs.** Un modèle de 7 milliards de paramètres sur un poste bureautique lit
moins bien : il se trompe davantage, produit parfois du JSON malformé, et lit
l'arabe moins bien que le français. Cela ne le rend pas dangereux **parce que
l'architecture ne lui fait pas confiance** : chaque valeur doit citer une page
et un extrait relu mot pour mot sur le texte local (DT-35). Une valeur inventée
ne passe pas ce contrôle. Le mode de défaillance est donc « moins de champs
extraits », jamais « des champs faux acceptés ».

C'est la première fois dans ce projet qu'une exigence de rigueur posée pour
d'autres raisons rend possible une solution qu'elle n'avait pas anticipée.

**Deux réglages qui ne se devinent pas, et dont l'oubli est silencieux :**

* **`num_ctx`** — la valeur par défaut d'Ollama (2048 jetons) **tronque
  l'entrée sans rien signaler**. Le modèle répondrait sur des pages amputées, et
  les champs perdus deviendraient des « non vérifiable » que personne ne
  relierait à la cause. La fenêtre est donc toujours demandée explicitement, et
  le découpage en lots est calculé à partir d'elle (`budget_for`) et non à
  partir du budget d'un modèle de service ;
* **`format: "json"`** — Ollama contraint alors la sortie à être du JSON valide.
  Sans cela, un petit modèle rend du texte mêlé de commentaires, inexploitable.

**Ce qui reste non mesuré, et doit être dit :** aucun appel réel n'a été émis,
ici non plus. 16 tests couvrent le chemin avec un ouvreur factice. La qualité de
lecture d'un `qwen2.5:7b` sur un dossier réel en français et en arabe reste à
mesurer sur poste.

## DT-40 — Une alerte dont la cause a disparu doit disparaître avec elle

**Mesuré :** après un OCR réussi, **51 alertes « page non extraite »**
subsistaient alors que 7 pages seulement restaient illisibles.

**Cause :** `run_vigilance` n'ajoutait que les détections nouvelles et ne
retirait jamais les anciennes. Les alertes de couverture, entièrement dérivées
de la lisibilité des pages, survivaient donc à la disparition de leur cause.

**Ce que cela coûtait** dépasse le comptage : l'évaluateur voyait — et le
rapport reprenait — des alertes pour un problème résolu. Une liste d'alertes
dont une partie est fausse n'est pas une liste à demi utile, c'est une liste
qu'on cesse de lire.

**Décision :** une alerte encore au statut `A_VERIFIER`, c'est-à-dire jamais
examinée, est retirée lorsque sa signature n'apparaît plus dans le recalcul.
Ce que l'évaluateur a qualifié est conservé sans condition, même devenu sans
objet : le moteur ne réécrit jamais une décision humaine. Le retrait est
journalisé et compté.

## DT-41 — L'installateur recommandait encore le chemin payant

**Constat, dans le journal d'installation de l'évaluateur**, après que le mode
local soit devenu la voie recommandée :

> LECTURE SEMANTIQUE ASSISTEE (optionnel, recommande)
> Pour l'activer : **activer_hybrid_strict.bat (une cle API est requise)**

J'avais changé la recommandation dans le code, dans `status()`, dans le README
et dans la documentation — et laissé le message de fin d'installation pointer
vers le seul chemin que cet évaluateur ne peut pas emprunter. Le dernier écran
d'une installation est celui qu'on lit ; c'était le seul endroit où l'ancienne
recommandation subsistait, et donc le pire.

**Leçon de méthode :** un changement de recommandation touche autant de textes
que de lignes de code. La recherche de l'ancien nom (`activer_hybrid_strict`)
aurait suffi à le voir.

## DT-42 — Le paquet français manquait, et le contrôle ne le disait pas

**Mesuré sur le poste :** Tesseract présent avec `ara, eng, osd`. Pas de `fra`.
Le contrôle d'installation affichait « Paquet arabe « ara » : présent » et
**restait muet sur le français**.

Cette absence ne fait rien échouer : `effective_languages()` restreint les
langues demandées à celles installées, et l'OCR continue. Les pages françaises
sont alors lues **avec le modèle anglais** — accents et ligatures dégradés,
sans le moindre message.

Or le français est la langue **principale** des dossiers de la commission.
Vérifier l'arabe et taire le français, c'est contrôler la langue minoritaire et
ignorer la majoritaire. Le contrôle signale désormais les deux, avec le remède
exact : `reparer_ocr_arabe.bat` en administrateur, qui pose aussi le français.

**Pourquoi la pose automatique avait échoué :** `installer_arabe.py`, appelé
depuis `install_windows.bat` non élevé, ne peut pas écrire dans
`C:\Program Files\Tesseract-OCR\tessdata`. Il l'a dit correctement et a nommé
le remède. Ce n'est pas un défaut — c'est la limite d'un installateur qui ne
demande pas les droits d'administrateur pour l'ensemble de son exécution, ce
qui reste le bon choix.

## DT-43 — Le battement n'était émis qu'au début de chaque étape

**Ce que l'évaluateur observait :** « Pages traitées : 67/76 » figé, 28 % qui ne
bouge pas, et la question naturelle — est-ce que ça travaille encore ?

Les 28 % sont normaux : c'est la valeur fixe de l'étape OCR, seul le compteur de
pages avance. Mais la question a mis au jour deux défauts réels, de même cause :
`heartbeat` n'était appelé qu'une fois, dans `_set_state`, **au démarrage** de
chaque étape.

**Le bail expirait pendant le travail.** Il dure 120 secondes. L'OCR d'un dossier
de 76 pages en demande plusieurs centaines ; une lecture par modèle local, dix à
vingt fois plus. `heartbeat_at` restait donc figé pendant toute l'étape, et rien
ne distinguait un worker à l'ouvrage d'un worker mort — exactement la distinction
que ce champ existe pour établir, et que l'en-tête du module annonce.

Avec un seul fil d'exécution, la conséquence restait théorique. Elle cessait de
l'être dès qu'un second worker, un redémarrage ou une reprise entrait en jeu :
un bail expiré autorise la réclamation d'un travail pourtant en cours.

**« Annuler » restait sans effet** jusqu'à la fin de l'étape. La demande était
lue par `_set_state`, donc **entre** deux étapes seulement. Sur une lecture de
quarante minutes, l'évaluateur pouvait cliquer, voir le bouton réagir, et
attendre. Un bouton qui ne répond pas n'est pas un bouton.

**Décision :** `pipeline._keepalive` renouvelle le bail et relit la demande
d'annulation, au rythme de `HEARTBEAT_SECONDS`, à l'intérieur des deux boucles
longues — l'OCR page par page et la lecture lot par lot. La relecture suit la
validation de transaction du battement : sans cela, la session du worker ne
verrait jamais la demande posée par l'interface dans une autre session.

Appeler la base à chaque page coûterait plus que la fraîcheur ne rapporte ; le
rythme est donc temporel, pas événementiel.

## DT-44 — Le message jetait la seule information utile

**Copie d'écran, mode `LOCAL_MODEL` actif, 76 pages océrisées :**

> L'étape « Lecture sémantique assistée du dossier » n'a pas abouti : l'appel au
> modèle n'a pas abouti. […] Ce contrôle nomme la cause exacte : **clé refusée,
> crédit absent**, modèle inconnu ou réseau bloqué.

L'étape était correctement nommée (DT-38 tenait). Mais le message parlait de
**clé** et de **crédit** à un évaluateur qui fait tourner un modèle sur son
propre poste, sans clé, sans compte et sans facture — l'envoyant chercher une
panne qui ne peut pas exister dans ce mode.

Deux défauts distincts, réparés ensemble.

**Le texte n'était pas adapté au mode.** `CONFIGURATION_ACTION` était unique. Il
existe maintenant en deux versions, et le mode local énumère ses propres causes :
serveur Ollama arrêté, modèle non téléchargé, modèle trop lent pour le poste.

**Le motif précis était écarté.** `_explain` remplaçait le message de l'exception
par une formule générique. Or ce message est composé par cette application : il
nomme la cause — délai dépassé, serveur injoignable, modèle absent — et souvent
le remède. Le jeter revenait à écarter la seule information utile, au profit
d'une phrase qui n'en portait aucune. Il est désormais concaténé à la cause. Il
ne contient jamais de secret : aucune clé n'est lue ni recopiée dans ces
messages.

**La cause la plus probable, et la plus invisible :** le délai. Un modèle de
14 milliards de paramètres sur un poste sans carte graphique met plusieurs
minutes par lot ; le plafond était à 900 secondes. Un dépassement de délai
ressemblait à une panne alors que le modèle **travaillait**. Il est maintenant
distingué explicitement, avec ses trois remèdes classés par efficacité : un
modèle plus petit, une fenêtre de contexte plus courte — qui réduit d'autant la
taille de chaque lot — ou un délai plus large.

## DT-45 — Trois scripts, deux commençant par « activer », un seul pertinent

**Constat d'usage, en deux temps.** L'évaluateur, qui voulait faire lire ses
dossiers par le modèle installé sur son poste, a lancé successivement :

1. `activer_local_only.bat` — qui a **désactivé** la lecture ;
2. `activer_hybrid_strict.bat` — qui lui a demandé une **clé API payante** qu'il
   n'a pas.

Aucune de ces deux tentatives n'était déraisonnable. C'est le nommage qui l'était.

**Le mot « local » désignait deux choses opposées.** `LOCAL_ONLY` se lit comme
« tout reste local » — exactement ce que cherche un évaluateur soucieux de
confidentialité — alors qu'il désigne l'**absence** de lecture. Et deux scripts
sur trois commençaient par `activer_`, dont un qui retire une capacité.

**Corrections :**

* `activer_local_only.bat` devient **`desactiver_lecture_semantique.bat`** : le
  nom dit ce que le script fait. Sa bannière affiche les trois modes, l'état
  courant du poste, et ce qui sera perdu — avant la question ;
* le message du mode `LOCAL_ONLY` ne se contente plus de dire qu'il « ne fournit
  pas le même niveau » : il énonce **« aucune lecture sémantique »**, et nomme
  l'issue — installer un modèle local ;
* un fichier **`MODES.txt`** à la racine répond à la seule question qui se pose :
  quel script lancer. Réponse : un seul.

**Ce que l'épisode enseigne.** J'ai ajouté un troisième mode en gardant les noms
des deux premiers, qui n'étaient distinctifs que tant qu'ils n'étaient que deux.
Un vocabulaire cohérent à deux termes peut devenir trompeur au troisième — et
c'est l'utilisateur qui paie la vérification.
