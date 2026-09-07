# PLAGENOR 4.0 — revue transversale et circuit OHB

Revue du 7 septembre 2026, base Git `2237f618` (PR #25). Ce document distingue les contrôles exécutés des éléments restant à prouver en production. L’objectif de 9,9/10 ne constitue pas une certification acquise.

## Décisions fonctionnelles

- Le dépôt public conserve deux parcours : IBTIKAR et demande commerciale. La troisième affectation OHB est un **circuit de facturation interne**. Le client ne dispose d’aucun sélecteur GenoClab/OHB.
- Seul le rôle `PLATFORM_ADMIN` (Admin Ops) peut affecter ou confirmer ce circuit avant émission du devis. La confirmation est obligatoire même pour GenoClab ; le rôle Superadmin ne contourne pas cette responsabilité opérationnelle.
- OHB utilise le tarif commercial comme base de préparation. L’émetteur est exactement **École Supérieure en Sciences Biologiques d’Oran** ; TVA non applicable selon l’instruction de l’établissement. Les coordonnées fiscales et bancaires OHB sont configurables séparément de celles de la filiale.
- L’accueil et l’aide présentent IBTIKAR comme ouvert à tous les étudiants algériens, quel que soit leur établissement. Le financement demeure soumis à validation du dossier et du financement. La migration actualise le contenu CMS existant en français, anglais et arabe.

## Finance, documents et traçabilité

| Étape | Responsable | Contrôle |
|---|---|---|
| Affectation GenoClab/OHB | Admin Ops | Interne, tracée, verrouillée après émission |
| Préparation et émission du devis/proforma | Administrateur habilité | Lignes, quantités, montants finis, TVA, validité, affectation confirmée |
| Acceptation ou refus | Client propriétaire | Devis communiqué, non expiré |
| Dépôt du bon de commande | Client propriétaire | Acceptation préalable, fichier contrôlé |
| Émission de la facture | Administrateur habilité | Bon de commande déposé, numérotation, copie des données d’émission |
| Dépôt ordre/mandat de paiement | Client propriétaire | Référence, date et pièce ; aucune confirmation automatique d’encaissement |
| Vérification du paiement | Rôle financier autorisé | Circuit existant de preuve et validation d’encaissement |

Un devis refusé peut faire l’objet d’une révision tracée, avec archivage des données antérieures et nouvelle référence. Les montants et identités des nouveaux documents émis sont conservés et protégés contre les modifications ordinaires. Le changement du tarif, du profil client ou du contenu institutionnel ne les recalcule plus.

Les anciens documents sans copie d’identité acquièrent une copie datée lors de leur première consultation. Cette récupération ne prouve pas l’identité exacte à leur date d’émission et ne reconstitue pas les anciens numéros qui n’étaient pas enregistrés. Les anciens exemplaires signés doivent rester les références documentaires.

Les notes budgétaires utilisent le prix enregistré et l’éventuelle validation administrative, sans consulter le tarif du jour. Les lignes de tableaux sont maintenues sur une même page. Les anciens exemples monétaires figés des formulaires ont été neutralisés. Les calculs et arrondis financiers utilisent `Decimal`, y compris les taux comportant des décimales en pourcentage.

## Visibilité et administration

L’écran **Tarifs et visibilité financière** permet de gérer :

- affichage global des estimations ;
- activation des estimations par prestation et masquage par demande ;
- identités et coordonnées séparées des deux émetteurs ;
- mode et délai de paiement des prochaines factures ;
- accès aux prestations et à leurs tarifs ;
- historique des décisions financières.

Le masquage est appliqué sur le serveur aux pages, fragments, API d’estimation et téléchargements concernés. Il ne supprime aucun montant interne. Les documents déjà communiqués restent accessibles à leur destinataire.

Les périodes tarifaires sont inclusives. Un tarif actif expiré n’entraîne pas de repli silencieux vers un ancien prix forfaitaire. Les modificateurs des champs configurables sont appliqués par le calculateur canonique dans l’ordre des champs : ajout, remplacement ou multiplication. Ils s’appliquent aussi après un tarif de base défini en base. Toute configuration invalide doit être corrigée avant publication d’une estimation.

L’écran **Modèles des notifications par e-mail** permet aux administrateurs habilités de modifier les objets et introductions des six événements dans les trois langues. Les références, destinataires et liens sécurisés restent gérés par l’application. Les modifications sont tracées ; le contenu libre est échappé.

## Vérifications exécutées localement

- Suite Django complète : **340 tests réussis**, couverture **90,57 %**, seuil de 90 % conservé sans exclusion supplémentaire.
- Contrôles Django, migrations et compilation des modèles HTML et traductions.
- Tests de parcours HTTP OHB : affectation, devis sans TVA, acceptation, bon de commande, émission de facture, verrouillage et contrôle d’accès.
- Tests des périodes tarifaires, modificateurs, arrondis, TVA fractionnaire, révisions, documents historiques, masquage et séparation des rôles.
- Échange SMTP réel sur une connexion TCP locale avec le backend SMTP Django ; vérification du destinataire, du MIME texte/HTML et des liens absolus. Ce contrôle valide le transport jusqu’au serveur de recette, **pas la réception dans une boîte de production**.
- Modèles e-mail rendus en FR/EN/AR, personnalisation, échappement HTML, absence de doublon sur les événements dédiés, détection des erreurs/refus du backend.
- 28 documents générés sur huit prestations et les deux émetteurs commerciaux, convertis en **58 pages PDF**, sans échec. Revue visuelle des planches et de pages ciblées, dont facture OHB et justification budgétaire.
- Scan Bandit : aucun résultat moyen ou élevé. Les avertissements de niveau faible ne constituent pas une preuve de pentest.
- Catalogues EN/AR : aucune entrée active non traduite ou marquée floue après extraction. Cela ne certifie pas la traduction des textes historiques non marqués ou des documents importés.

La suite navigateur CI a été enrichie : paramètres financiers, modèles d’e-mail et parcours OHB avec devis, bon de commande et facture, sur Chromium, Firefox et mobile Chromium. Son résultat final doit être consulté sur la PR. Le navigateur contrôlé local était bloqué sur l’URL de recette ; aucune réussite locale de ces scénarios n’est revendiquée.

## Vérification documentaire et réglementaire

- [Ministère du Commerce, décret exécutif 05-468](https://www.commerce.gov.dz/fr/reglementation/decret-executif-n05-468) et [texte au JORADP](https://www.joradp.dz/FTP/jo-francais/2005/F2005080.pdf) : cadre de la facturation et mentions documentaires. Le bon de commande préalable est ici une règle interne, pas une obligation légale universelle affirmée par l’application.
- [Loi 23-07 relative à la comptabilité publique](https://www.joradp.dz/FTP/JO-FRANCAIS/2023/F2023042.pdf), articles 55 à 59 : distinguer engagement, liquidation, ordonnancement/mandatement et paiement. Un ordre de paiement téléversé ne vaut pas encaissement.
- [MESRS, arrêté 533 du 23 juin 2013](https://services.mesrs.dz/DEJA/fichiers_sommaire_des_textes/238%20BIS%20FR.PDF), notamment articles 4, 5, 10 et 11 : prestations contractuelles, autorisation de l’établissement et suivi des recettes hors budget.
- [DGRSDT, présentation d’IBTIKAR](https://dgrsdt.dz/en/blog/ibtikar-platform/73) : plateforme nationale de services pour les projets étudiants et la recherche. L’ouverture à tous les étudiants algériens dans PLAGENOR applique la demande de son administrateur ; elle ne promet pas une prise en charge automatique.

Le non-assujettissement à la TVA de l’ESSBO est un **paramètre institutionnel fourni par le responsable**, et non une conclusion fiscale indépendante tirée de ces sources. Les mentions légales, comptes et identifiants effectivement utilisés doivent correspondre aux documents institutionnels de chaque émetteur.

## Preuves encore nécessaires avant une note de production de 9,9/10

1. CI du commit publié et révision exacte effectivement déployée. Les endpoints de santé exposent désormais `X-PLAGENOR-Revision` lorsque Render fournit un SHA valide.
2. Réception réelle d’un e-mail depuis la configuration SMTP de production, preuve du destinataire et examen des erreurs/rejets. Aucun envoi à un collaborateur non autorisé n’a été effectué pendant cette recette.
3. Exécution du scénario de restauration avec les données et secrets de sauvegarde de production ; une restauration synthétique CI ne remplace pas cet exercice.
4. Revue manuelle d’accessibilité, lecteurs d’écran et rendu multilingue des documents administratifs et scientifiques historiques. Certains contenus importés restent dans leur langue d’origine.
5. Pentest externe et revue fiscale/institutionnelle des identifiants d’émetteur. La CSP conserve encore du JavaScript inline dans des écrans existants.

## Mise en service

Appliquer les migrations avec le processus habituel avant de démarrer cette version. Vérifier les identités GenoClab et OHB dans les paramètres financiers. L’Admin Ops doit confirmer le circuit des devis encore en préparation avant de les envoyer. Les numéros de brouillons retirés ne sont pas réutilisés.

Les nouveaux fichiers d’ordres de paiement utilisent le stockage privé et les autorisations existants. Les paramètres SMTP et les secrets de chiffrement ne sont pas modifiés par cette livraison.
