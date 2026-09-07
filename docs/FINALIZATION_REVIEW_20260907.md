# PLAGENOR — revue de finalisation du 7 septembre 2026

## Conclusion et portée

Cette livraison corrige des omissions réelles de la PR #27. La phrase qui limitait IBTIKAR à l’ESSBO était encore enregistrée dans le CMS : modifier uniquement un template ne pouvait pas la remplacer. La migration 0028 corrige le contenu existant en français, anglais et arabe. IBTIKAR est présenté comme accessible aux étudiants algériens, quel que soit leur établissement, sous réserve des conditions du dispositif.

L’objectif 9,9/10 **n’est pas certifié**. L’appréciation technique provisoire est **9,2/10 sur le périmètre testé**. Ce nombre est un jugement, pas une métrique de conformité. Les réserves ci-dessous empêchent de qualifier l’application entière de définitivement finalisée.

## Matrice des exigences et preuves

| Exigence | Vérifications et corrections de cette livraison | Limite de la validation |
| --- | --- | --- |
| Documents | Génération des formulaires IBTIKAR, notes de plateforme, fiches de réception, devis et factures GenoClab/OHB, facture annulée et rapport statistique. DOCX convertis en PDF, pages inspectées. Suppression du bloc IBTIKAR « à remplir » redondant, données avant signature, booléens/libellés français, marges adaptées au bandeau, montant administratif cohérent. | Les modèles institutionnels restent principalement français avec le bandeau fourni en anglais. Toutes les variantes de modèles importés et leurs langues n’ont pas été inspectées. |
| Estimations | Masquage côté demandeur/client/visiteur, expiration de publication, montant interne conservé, accès direct au devis brouillon refusé. Le navigateur appelle le calcul canonique du serveur ; les anciennes formules JavaScript indépendantes sont retirées. Tarifs hors période refusés. | La validation organisationnelle de chaque tarif réel reste à la charge des administrateurs. |
| Workflow commercial | Bon de commande → facture → affectation imposé. Une transition ne peut pas prétendre qu’une facture existe sans facture active. Émission unique sous verrou, régularisation motivée des anciens dossiers sans changer leur état, note et pièce exigées avant confirmation de règlement. | Une facture déjà encaissée même partiellement ne peut pas être simplement annulée. Le traitement comptable par avoir n’est pas implémenté. |
| OHB | Affectation exclusivement Admin Ops, verrouillée après émission. Identité ESSBO et TVA 0 conservées avec les documents. Historique administratif interne filtré des chronologies clientes. Revenus et archives OHB séparés de GenoClab ; factures annulées exclues. | Les coordonnées fiscales, bancaires, la forme juridique et les mentions applicables doivent être confirmées par l’établissement. Le non-assujettissement OHB est appliqué sur instruction du propriétaire, sans certification fiscale indépendante. |
| Notifications/e-mails | Liens absolus selon le rôle du destinataire ; suppression des doublons e-mail générique + rendez-vous/rapport ; fin de la fausse confirmation de paiement lors du simple dépôt d’une pièce. Objets FR/EN/AR, corps arabe/RTL, partie texte, erreur si le backend n’accepte pas le message. Test SMTP réel vers un serveur récepteur local isolé. | La réception d’un e-mail envoyé par Render dans une boîte externe n’est pas démontrée. Les erreurs sont journalisées ; il n’existe pas de file de reprise durable de tous les e-mails. |
| Icônes/accessibilité | Navigation SVG décorative explicitement masquée aux lecteurs d’écran ; badges monétaires SVG ; icônes emoji des nouveaux e-mails supprimées. Contrôles automatisés WCAG 2.2 AA sur pages publiques, rôles, langues, catalogue Ops et visibilité financière. | Ceci ne remplace pas une revue manuelle exhaustive avec lecteurs d’écran de tous les états de chaque écran. |
| Administration | Catalogue opérationnel et modification des prestations/tarifs accessibles à Admin Ops ; gestion des utilisateurs/sécurité toujours réservée au Superadmin. Validation avant mutation des prix, multiplicateurs, délais et configurations JSON. Émetteurs éditables dans le CMS, champs OHB visibles après seed_content ; coordonnées clients et conditions commerciales saisissables lors du devis. | Les équipements n’ont pas de module de gestion autonome. Les transitions sensibles sont codifiées ; les corps des modèles d’e-mail ne sont pas intégralement éditables dans l’interface. |
| Historique financier | Originaux émis conservés en base dans IssuedDocument avec SHA-256. Téléchargements identiques après modification du CMS ou des tarifs ; altération détectée. Révision d’un devis refusé avec nouvelle référence, ancien original conservé. Annulation motivée, copie marquée en diagonale, original non altéré. | Un document émis avant cet archivage et jamais conservé ne peut pas être reconstitué avec certitude si ses anciennes coordonnées ont déjà changé. |
| Revue générale | Tests des parcours complets IBTIKAR/GenoClab, autorisations, uploads, liens, tableaux financiers, archives, protections d’accès et scénarios d’erreur. Export personnel inspecté : pas d’affectation interne ni de données financières masquées. | Chaque combinaison de rôle, données, équipement, navigateur et état n’a pas fait l’objet d’un parcours manuel. |
| Traductions/recherche | Catalogues EN/AR sans entrée active vide ou fuzzy après extraction ; nouveaux réglages et états traduits. Recherche officielle ciblée IBTIKAR/facturation. L’attribution juridique erronée de l’obligation de bon de commande est retirée du message client. | Les catalogues complets ne prouvent pas l’absence de chaînes codées en dur. Les contenus métier configurés par les administrateurs et les documents français restent à revoir pour une couverture multilingue intégrale. |

## Tests reproductibles

- `DEBUG=true SECRET_KEY=local-test ../venv/bin/python -m coverage run manage.py test --noinput` : **351 tests réussis** en 48,374 secondes sur SQLite local.
- `coverage report` : **90,88 %**, seuil de dépôt **90 % conservé**.
- `manage.py makemigrations --check --dry-run` : aucune migration manquante.
- `manage.py check`, `compilemessages`, `collectstatic`, `git diff --check` : vérifiés.
- Playwright : 24 scénarios par projet, Chromium ordinateur et mobile. 47/48 au premier passage ; le dernier échec venait du test qui essayait de cliquer le sélecteur de langue d’une barre latérale repliée. Après correction du test, les 2 scénarios ciblés ordinateur/mobile passent. **48 scénarios distincts validés**.
- Firefox local : échec du processus navigateur avant ouverture de page (`uid_map: EPERM`, processus enfant signal 11). Résultat GitHub CI à contrôler, sans compter cette tentative comme succès.
- SMTP : véritable connexion réseau locale, message reçu et analysé, destinataire/objet/parties texte et HTML vérifiés. Aucun message de test adressé à un client réel.
- Documents : neuf variantes générées ; contrôle des dix pages initiales, puis nouveau rendu des documents corrigés et de la marque d’annulation. Données de démonstration isolées, sans accès aux dossiers de production.

## Déploiement et preuves opérationnelles

La base de cette branche est `eaec23d262e72e3afca1f68b0c10d888b31cc6b2`, PR #27 déjà fusionnée. Les résultats de CI et le déploiement de cette nouvelle livraison doivent être établis séparément.

Les commandes Render sont désormais accessibles. Le connecteur exige la confirmation de l’espace « My Workspace » avant de consulter les services. La fusion de la PR #28 a été rejetée par le contrôle automatique d’approbation, faute d’autorisation de fusion/déploiement jugée explicite. Aucun déploiement de cette PR n’est confirmé.

Restent indispensables : sauvegarde/restauration de production avec chiffrement et manifeste, réception SMTP externe, validation des identités de facturation et revue des réserves fonctionnelles ci-dessus. Aucun secret n’est enregistré dans ce bilan.

## Sources officielles et qualification

- [DGRSDT — Ibtikar platform](https://dgrsdt.dz/en/blog/ibtikar-platform/73) : dispositif destiné notamment aux étudiants porteurs de projets de fin d’études ; la présentation n’établit pas de restriction à l’ESSBO. Le périmètre national demandé est appliqué comme instruction fonctionnelle du propriétaire.
- [Ministère du Commerce — Facture](https://www.commerce.gov.dz/fr/questions-frequentes/themes/facture) : mentions du vendeur et de l’acheteur, numérotation/date, taxes et identification d’une facture annulée.
- [Décret exécutif n° 05-468](https://www.commerce.gov.dz/fr/reglementation/decret-executif-n05-468) : cadre de facturation cité par le ministère.
- Le bon de commande obligatoire dans cette application relève du **workflow interne demandé**. La réception d’un ordre de paiement n’est pas assimilée à une confirmation bancaire d’encaissement.

## Complément — notifications de règlement

La relance après analyse utilise maintenant la facture active émise, et non le prix mutable de la demande. Aucune relance n’est créée sans facture, pour une facture annulée, payée ou à zéro. Un statut de paiement partiel ne comportant pas de montant encaissé, le message invite à contacter le service financier sans inventer de solde. Le montant conserve ses décimales ; le message et son lien respectent la langue FR/EN/AR du destinataire. L’écran analyste n’annonce plus un envoi lorsque la relance a été omise.

Le commit précédent de la PR #28 a réussi les quatre contrôles GitHub (SQLite, PostgreSQL, 72 scénarios navigateur dont Firefox, conteneur), avec 351 tests et 90,88 % de couverture. Les résultats de ce complément sont à distinguer de cette exécution.

Validation du complément : 353 tests locaux réussis en 51,311 s ; couverture 90,86 %, seuil 90 % conservé. Les 21 tests de notifications passent également isolément.

## Mesure de couverture et disponibilité Render

La configuration précédente incluait par erreur les fichiers `test_*.py` : 1 169 lignes de tests exécutées gonflaient le résultat de 89,66 % (code applicatif) à 90,86 %. Le motif d’exclusion est corrigé, sans exclure de nouveau code applicatif ni réduire le seuil CI de 90 %.

Sept tests de contrats supplémentaires couvrent les dates de lecture et leur stabilité, la séparation des comptes, les redirections externes, les rôles, les tarifs invalides et leurs mises à jour atomiques, les priorités de calcul et la charge des analystes. Deux défauts sont corrigés : dates de lecture non enregistrées par les vues et productivité zéro remplacée par la valeur par défaut. Validation locale : 359 tests puis les 7 tests ciblés (360 tests distincts au total), tous réussis. Couverture combinée : 90,29 %, 866 lignes manquantes sur 8 922. L’objectif 99,99 % n’est pas atteint ; avec ce périmètre il nécessiterait de couvrir toutes les lignes. La couverture des lignes n’est pas une preuve d’exhaustivité fonctionnelle ou de couverture des branches.

Le service Render `plagenor`, associé au dépôt attendu et à `main`, utilise le plan `free` avec déploiement automatique activé. La documentation officielle confirme la veille après 15 minutes d’inactivité et le blocage SMTP sortant sur 25/465/587 pour ce plan. Une instance de calcul payante élimine la veille ; l’offre d’entrée est annoncée à 7 USD/mois pour le calcul seul. Aucun changement payant n’a été appliqué sans accord sur le coût. Un changement du plan de l’espace de travail seul ne supprime pas la veille des instances gratuites.

Sources : https://render.com/docs/free ; https://render.com/docs/faq ; https://render.com/pricing.
