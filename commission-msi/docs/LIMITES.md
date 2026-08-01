# Limites de l'application

*Designed by Prof. Merzoug Mohamed.*

Ces limites sont affichées dans l'application (`GET /api/v1/limites`) et
reproduites en dernière section de chaque rapport.

## Fiabilité générale

1. Aucune garantie d'exhaustivité ni de zéro erreur. L'objectif tenu est
   **zéro erreur silencieuse**, pas zéro erreur.
2. L'absence d'alerte ne prouve pas l'absence de risque.
3. Une erreur technique interrompt l'action et conserve l'état précédent ; elle
   ne produit jamais de résultat partiel présenté comme valide.

## Extraction et OCR

4. L'OCR est particulièrement fragile pour les noms propres, les dates, les
   montants et l'arabe.
5. La détection textuelle ne suffit pas pour les drapeaux, cartes, logos,
   tampons et signatures : ces éléments exigent un examen visuel humain.
6. Une page non extraite produit une alerte de couverture : elle peut contenir
   un terme sensible non détecté.
7. Si Tesseract n'est pas installé, l'OCR échoue explicitement. L'application ne
   devine jamais un contenu.

## Règles et droit

8. Les règles officielles sont susceptibles d'évoluer.
9. Une règle sans source officielle validée est une règle de **vigilance** :
   elle demande une vérification et n'est jamais une interdiction.
10. La qualification juridique et diplomatique est réservée aux autorités
    compétentes, sur le seul fondement d'un texte algérien officiel validé.
11. Une contradiction entre sources produit `CONTRADICTION_A_ARBITRER` : elle
    n'est jamais arbitrée automatiquement.

## Appréciation

12. L'appréciation scientifique est réservée à l'évaluateur. Le système ne
    propose jamais de note et ne calcule que la somme des notes saisies.
13. Aucune alerte ne peut produire une note, une conformité ou une décision.

## Module en ligne

14. Les résultats Web dépendent de la disponibilité, de l'indexation, de la
    langue et de la date de consultation.
15. L'absence de résultat Web ne prouve ni l'absence d'activité ni l'absence de
    risque.
16. Risque d'homonymie, de contenu obsolète, de désinformation et de biais des
    moteurs ou des agents.
17. Une association, une présence à un événement, une signature collective ou un
    abonnement ne prouvent pas l'adhésion à toutes les positions d'une
    organisation, et ne constituent pas une incompatibilité.
18. Le ranking IA est indicatif, non homologué, et ne remplace ni l'évaluation
    réglementaire ni l'appréciation scientifique humaine.
19. Un désaccord entre agents ou une homonymie possible bloque toute conclusion
    consolidée.

## Protection

20. Prototype local, non équivalent à une plateforme institutionnelle
    homologuée.
21. Le chiffrement applicatif ne remplace pas le chiffrement complet du disque.
22. Les métadonnées minimales de recherche locale restent en clair dans la base.
23. Toute personne ayant un accès interactif au poste déverrouillé accède aux
    dossiers : l'application n'a ni compte ni mot de passe.
