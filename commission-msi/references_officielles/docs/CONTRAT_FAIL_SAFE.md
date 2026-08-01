# Contrat de fiabilité et de non-hallucination

## Limite honnête

Aucun OCR, logiciel ou modèle ne peut garantir une absence absolue d'erreur. L'application doit viser l'absence d'erreur silencieuse : toute incertitude est visible, traçable et bloque la conclusion automatique.

## Invariants non négociables

1. Le PDF original est immuable, chiffré et identifié par SHA-256.
2. Chaque fait affiché possède un document, une page, un passage, un mode d'extraction et une confiance.
3. Le texte OCR n'écrase jamais le texte initial et n'est jamais déclaré certain par défaut.
4. Une correction humaine crée une nouvelle version et conserve l'ancienne.
5. Une règle ne peut être active sans code, version, autorité, source, page ou passage, champ d'application et validation.
6. Une proposition, un guide non adopté ou un manuel de travail ne devient jamais une norme.
7. Une détection géopolitique, une nationalité, une affiliation ou un pays ne produit jamais une décision.
8. Le moteur calcule uniquement des totaux saisis par l'évaluateur ; il ne note pas.
9. Une contradiction entre sources produit `CONTRADICTION_A_ARBITRER`, jamais une interprétation automatique.
10. Toute donnée incertaine utilisée dans un rapport est étiquetée `A_VERIFIER` ou exclue de la synthèse factuelle.
11. Aucune IA générative ni API externe n'intervient dans le chemin de décision par défaut.
12. L'absence d'alerte ne peut jamais être affichée comme preuve d'absence de risque.
13. Les tests utilisent exclusivement des dossiers fictifs.
14. La sauvegarde et la restauration sont vérifiées sur copie avant usage réel.
15. Une erreur technique interrompt l'action et conserve l'état précédent ; elle ne doit pas produire de résultat partiel présenté comme valide.

## Portes de validation

- `G0_SOURCE` : source identifiée et empreinte vérifiée ;
- `G1_EXTRACTION` : page lisible ou marquée incertaine ;
- `G2_ADMINISTRATIF` : pièces contrôlées manuellement ;
- `G3_ELIGIBILITE` : critères documentés avec preuve ;
- `G4_SCIENTIFIQUE` : notes saisies et justifiées par l'évaluateur ;
- `G5_VIGILANCE` : alertes qualifiées et motivées ;
- `G6_RAPPORT` : aucune affirmation orpheline de source ;
- `G7_VALIDATION_HUMAINE` : rapport explicitement validé avant export officiel.

Une porte non satisfaite bloque uniquement l'étape suivante ; elle ne transforme pas le dossier en rejet.

## Tests négatifs obligatoires

Le système doit prouver qu'il refuse : faux PDF, mauvaise clé, champ sans source, règle sans validation, score hors limites, conclusion sans motivation, alerte transformée en rejet, écrasement d'un original, rapport contenant un fait sans page et redirection avant validation de la transaction SQLite.
