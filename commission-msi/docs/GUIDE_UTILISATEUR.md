# Guide utilisateur

*Designed by Prof. Merzoug Mohamed.*

> L'application extrait, vérifie, classe, compare, signale et prépare.
> Vous contrôlez, interprétez, appréciez et décidez.

## 1. Démarrage

Lancez `run_windows.bat`. Le tableau de bord s'ouvre directement : aucun compte,
aucun identifiant, aucun mot de passe. Si le serveur n'est pas prêt, un message
explicite s'affiche — sans boucle de redirection.

L'en-tête permet de basculer entre **français, anglais et arabe** ; l'arabe
passe l'interface en lecture de droite à gauche.

## 2. Tableau de bord

Il affiche les dossiers récents, le nombre d'alertes ouvertes, les pages
nécessitant un OCR, les pièces manquantes et les rapports générés, avec filtres
par statut, organisateur et priorité, et une recherche globale.

Un indicateur séparé montre la connectivité Internet et l'état des fournisseurs
de recherche. Hors ligne, le cœur documentaire reste pleinement utilisable.

## 3. Créer un dossier

Renseignez **référence**, **intitulé** et **organisateur**. Le dossier est créé
à l'état `NOUVEAU` avec sa liste de pièces, sa liste de contrôle administratif
et ses champs d'information.

## 4. Onglet « Document »

Importez le PDF original : il est validé, empreinté (SHA-256), chiffré et
conservé **sans aucune modification**.

L'écran partagé montre la page originale et le texte extrait, avec le mode
d'extraction, la confiance et les anomalies (page blanche, difficile, doublon
probable, OCR requis).

- **Lancer l'OCR local** : uniquement quand c'est nécessaire ou demandé. Le
  texte OCR ne remplace jamais le texte initial.
- **Corriger le texte** : un motif d'au moins 8 caractères est obligatoire ; la
  valeur initiale est conservée et l'historique tracé.
- **Rechercher dans le texte** : chaque résultat renvoie directement à sa page.

Si la confiance est inférieure à 65 % ou le texte utile trop court, le message
suivant s'affiche : *Contenu illisible ou insuffisamment fiable — vérification
humaine obligatoire.*

## 5. Onglet « Pièces »

Chaque pièce est proposée avec un statut. **La détection d'un titre ne vaut
jamais confirmation de la validité de la pièce.** Vous seul qualifiez une pièce,
avec un commentaire obligatoire. Les documents d'identité sont en section
restreinte et masqués dans les écrans et exports ordinaires.

## 6. Onglet « Informations »

Pour chaque champ : valeur proposée, valeur initiale, page source, extrait
source, mode d'extraction, confiance et statut.

**Une information confirmée exige une page et un passage source**, ou une case
« saisie manuelle validée » cochée explicitement. Sans cela, l'enregistrement
est refusé. Les champs à contrôle renforcé (noms, dates, montants, pays,
institutions, affiliations, références réglementaires) sont signalés.

## 7. Onglet « Contrôle administratif »

Liste de contrôle éditable en dix-sept points. Chaque qualification autre que
`A_VERIFIER` exige une explication. Les rapprochements approximatifs de noms
affichent les deux graphies et la métrique utilisée, et demandent votre
confirmation.

## 8. Onglet « Évaluation scientifique »

Cinq critères, total 100. **Vous saisissez chaque note ; le système n'en propose
aucune.** Une note hors bornes est refusée sans valeur de remplacement. Une
justification est obligatoire. Le total n'est calculé que lorsque la grille est
complète — c'est une simple somme. Tout l'historique est conservé.

## 9. Onglet « Alertes et points sensibles »

Chaque alerte indique sa source, sa page, son contexte, sa confiance, sa raison,
la vérification recommandée et son statut humain.

La section **« Mentions relatives au Maroc — vérification institutionnelle
obligatoire »** est présentée séparément, avec le rappel : *Point de vigilance
institutionnelle — vérifier les instructions officielles applicables à la
session avant toute conclusion.* Vous qualifiez la relation (mention
géographique, référence bibliographique, affiliation, nationalité déclarée,
partenaire…). Une ville, un domaine, un indicatif ou une nationalité ne suffit
jamais à établir une collaboration et ne produit jamais d'avis défavorable.

Les statuts `CONFIRME`, `ECARTE` et `TRANSMIS` exigent une motivation d'au
moins 8 caractères. **Une alerte reste une alerte : elle ne devient jamais une
décision.**

## 10. Onglet « Recherche Web et ranking »

1. **Préparer une campagne** : l'application construit des requêtes candidates à
   partir des seules informations publiques du dossier.
2. **Relire chaque requête** : vous pouvez la modifier. Une requête contenant un
   document, un passeport, un courriel, un téléphone ou une donnée personnelle
   est refusée avant tout envoi.
3. **Approuver** puis **lancer** : seules les requêtes approuvées partent.
4. Les résultats sont enregistrés avec URL canonique, éditeur, date de
   publication, **date de consultation** et palier de source.
5. Six agents spécialisés analysent indépendamment et produisent des
   affirmations atomiques sourcées, distinguant fait vérifié, déclaration,
   allégation, opinion, rumeur et absence de preuve.
6. Une homonymie possible ou un désaccord entre agents affiche
   `DESACCORD_AGENTS — ARBITRAGE_HUMAIN_OBLIGATOIRE` et bloque toute conclusion
   consolidée.

Le **classement externe indicatif** (7 axes, total 100) est affiché avec ses
intervalles d'incertitude et ses sources. Un axe sans preuves suffisantes reste
`NR — NON RENSEIGNE`. Vous pouvez accepter, corriger ou écarter chaque axe avec
justification. **Ce classement ne modifie jamais la grille scientifique
officielle.**

Sans Internet : *Recherche Web indisponible — analyse enrichie incomplète,
vérification humaine externe obligatoire.*

## 11. Onglet « Notes et conclusion »

Notes, réserves et questions à la commission. La conclusion se choisit dans une
liste fermée de huit valeurs, avec motivation obligatoire, et porte toujours la
mention : *Proposition personnelle de l'évaluateur — ne vaut pas décision de la
commission.*

## 12. Onglet « Rapports »

Un **brouillon** filigrané peut toujours être produit. L'**export officiel**
exige la validation humaine (porte G7) et est bloqué si un fait est sans source
ou si une alerte reste au statut `A_VERIFIER`.

Le rapport distingue visuellement `FAIT_EXTRAIT`, `CALCUL`, `ALERTE_SYSTEME`,
`COMMENTAIRE_EVALUATEUR`, `CONCLUSION_EVALUATEUR` et `A_VERIFIER`, et porte en
première page : *Projet de rapport — validation humaine obligatoire.*

## 13. Onglet « Historique »

Journal complet des actions. Les valeurs sensibles n'y figurent jamais en
clair : seules des empreintes SHA-256.

## 14. Sauvegarde

Créez une sauvegarde horodatée depuis l'application. Elle contient une copie
cohérente de la base, les documents et rapports chiffrés, le référentiel actif,
`master.key` et un manifeste SHA-256. **Conservez-la sur un support chiffré.**

## 15. Lecture sémantique assistée (mode `HYBRID_STRICT`)

### Pourquoi l'activer

Sans elle, l'application ne repère que les informations écrites sous la forme
`Libellé : valeur` sur une seule ligne. Mesure faite sur un dossier réel de
76 pages : **4 champs sur 29, dont 2 faux**, alors que la page 12 énonçait en
clair l'intitulé, l'université, la faculté, le laboratoire, les dates et le
format. Un dossier réel est fait de blocs de titre, de tableaux et de prose.

Avec elle, le texte est **lu**, comme le ferait un rapporteur.

### Comment l'activer

Lancez `activer_hybrid_strict.bat`. Il demande l'identifiant exact du modèle,
puis la clé API — saisie masquée, jamais affichée, jamais écrite dans un fichier
du projet : elle est posée dans les variables d'environnement de votre session
Windows. Le script termine par **un appel réel de contrôle** : c'est le seul
moyen de savoir si la clé et le modèle fonctionnent vraiment, une configuration
complète pouvant parfaitement accompagner une clé révoquée.

Pour désactiver la lecture : `desactiver_lecture_semantique.bat`, qui efface
aussi la clé de service. **Attention au vocabulaire** : le mode `LOCAL_ONLY`
qu'il pose ne désigne pas le modèle local, mais l'absence de toute lecture
sémantique. Pour la lecture par un modèle local : `installer_modele_local.bat`.

Pour revérifier à tout moment, sans rien changer :

```
backend\.venv\Scripts\python.exe scripts\verifier_ia.py --appel
```

### Ce qui ne quitte jamais le poste

Le PDF original, les pièces d'identité, les numéros de passeport, et les pages
de tout document que vous avez classé `RESTREINT`. Ces refus sont écrits dans le
code, pas dans la configuration : aucune variable d'environnement ne peut les
ouvrir.

### Ce que le modèle ne fait pas

Il ne produit **ni statut, ni note, ni avis**. Les 26 critères, le score sur 100
et l'avis technique restent calculés par les moteurs déterministes, à partir des
valeurs une fois que **vous** les avez qualifiées.

### Comment lire la carte « Lecture sémantique assistée »

Elle affiche, au même rang, ce qui a été proposé **et ce qui a été rejeté**.
Chaque valeur devait citer sa page et un extrait ; l'extrait est relu mot pour
mot sur le texte de cette page, et la proposition est écartée s'il ne s'y trouve
pas. Un nombre de rejets non nul n'est pas un défaut : c'est le contrôle qui
fonctionne. Dépliez la liste pour voir lesquelles et pourquoi.

Toutes les valeurs retenues arrivent au statut **À vérifier**, avec leur page et
leur extrait. Aucune n'est confirmée : la confirmation vous appartient.
