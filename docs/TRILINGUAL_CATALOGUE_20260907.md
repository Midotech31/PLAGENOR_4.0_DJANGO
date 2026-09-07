# Catalogue français, arabe et anglais — 7 septembre 2026

## Correction

Les huit prestations du registre disposent de noms et descriptions en français, arabe et anglais. La migration 0031 remplace les champs vides et les copies des textes sources ; elle conserve les traductions personnalisées et les données financières.

Le catalogue, les fiches détaillées, les exigences, les livrables, les libellés et choix des formulaires ainsi que les détails des demandes utilisent la langue sélectionnée. Les codes techniques, séquences et valeurs enregistrées pour les calculs restent inchangés. L’aperçu avant envoi et les messages de validation JavaScript prennent également en charge l’arabe.

Les créations depuis le tableau de bord et l’administration Django exigent les six champs nom/description FR/AR/EN. Les champs personnalisés exigent leurs trois libellés. Les importations YAML incomplètes sont rejetées avant toute écriture.

Le réimport au démarrage préserve désormais les tarifs, les périodes, l’activation, les délais et les textes administrés. Il crée les services absents et complète uniquement les traductions vides. Les contenus saisis dans l’aperçu sont échappés pour empêcher leur interprétation comme HTML.

## Vérification

- Tests HTTP des huit prestations dans les trois langues, des fiches et des formulaires.
- Création incomplète rejetée côté serveur ; création complète dans une session arabe.
- Modification incomplète rejetée avant toute mutation financière.
- Contrôle des formulaires Django Admin et des champs personnalisés.
- Import idempotent et migration préservant les personnalisations et montants.
- Options traduites avec valeurs de calcul identiques ; registre partagé non modifié.
- Scénarios navigateur FR/AR/EN : catalogue, accessibilité, aperçu et champs obligatoires.
- La CI conserve le seuil de couverture des lignes à 100 %, sans nouvelle exclusion.

Cette livraison traite les contenus et parcours du catalogue. Elle ne constitue pas une certification linguistique exhaustive de chaque document historique, notification déjà enregistrée ou texte libre saisi par un utilisateur. Les descriptions et libellés futurs doivent être traduits par l’administrateur ; aucune traduction automatique approximative n’est publiée à sa place.

## Pertinence terminologique

Relecture ciblée à partir de sources institutionnelles et des fabricants, le 7 septembre 2026. Ces sources vérifient le vocabulaire ; elles ne certifient pas les prestations ni les capacités de PLAGENOR.

| Notion | Français | Arabe retenu |
| --- | --- | --- |
| PCR | Réaction en chaîne par polymérase | تفاعل البوليميراز المتسلسل |
| Whole genome sequencing | Séquençage du génome entier | تسلسل الجينوم الكامل |
| Primers | Amorces | بادئات |
| MALDI-TOF identification | Identification microbienne par spectrométrie de masse | التعرّف على الكائنات الحية الدقيقة باستخدام مطيافية الكتلة |
| Freeze-drying | Lyophilisation / séchage par congélation sous vide | التجفيف بالتجميد تحت التفريغ |

Références :

- [OMS — Guide de sécurité biologique en laboratoire, édition arabe](https://iris.who.int/server/api/core/bitstreams/64325d15-ecb5-4178-875a-a4631580a275/content) : usage de la terminologie PCR.
- [OMS — Séquençage génomique, édition arabe](https://iris.who.int/bitstreams/8be63990-3910-4418-a593-35fb53c6662c/download) : terminologie du séquençage et des amorces.
- [Bruker — Identification microbienne](https://www.bruker.com/fr/products-and-solutions/microbiology-and-diagnostics/microbial-identification.html) : distinction entre identification par empreinte protéique et séquençage génétique.
- [Thermo Fisher — Quantification fluorimétrique](https://www.thermofisher.com/fr/fr/home/industrial/spectroscopy-elemental-isotope-analysis/molecular-spectroscopy/fluorometers/qubit.html) : quantification des acides nucléiques.

Les noms de technologies et de formats (Illumina, Sanger, MALDI-TOF MS, FASTA, FASTQ) restent reconnaissables. Les traductions conservent les limites des prestations, notamment l’absence d’identification/interprétation pour le séquençage Sanger seul et l’absence de conception des amorces pour leur synthèse.

## Correction RTL sur mobile

Le contrôle navigateur a révélé que le menu latéral arabe fermé était déplacé vers l’intérieur de l’écran. La transformation CSS tient désormais compte de l’ancrage à droite. Les scénarios mobiles vérifient le menu fermé hors écran, son ouverture, sa fermeture et le changement de langue depuis la barre supérieure. Les trois scénarios ciblés FR/AR/EN passent localement.
