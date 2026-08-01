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
