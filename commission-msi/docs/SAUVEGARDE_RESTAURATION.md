# Sauvegarde et restauration

*Designed by Prof. Merzoug Mohamed.*

## 1. Contenu d'une sauvegarde

| Élément | Chemin dans l'archive |
|---|---|
| Copie cohérente SQLite (API `backup`, WAL inclus) | `base/commission_msi.sqlite3` |
| Clé maîtresse | `cle/master.key` |
| Documents chiffrés | `documents/` |
| Rapports | `rapports/` |
| Textes réglementaires chiffrés | `reglementation/` |
| Référentiel actif | `referentiel/default_rules.json` |
| Manifeste SHA-256 de chaque fichier | `MANIFESTE.json` |

> **Avertissement obligatoire.** Cette sauvegarde contient `master.key`. Sans
> cette clé, les données chiffrées sont définitivement illisibles ; avec elle,
> quiconque possède l'archive peut les lire. Conservez-la exclusivement sur un
> support chiffré (BitLocker recommandé).

## 2. Créer une sauvegarde

Depuis l'interface, ou :

```
POST /api/v1/sauvegardes
```

L'archive est vérifiée immédiatement après création. Si la vérification échoue,
la sauvegarde n'est pas considérée comme fiable.

## 3. Vérifier une sauvegarde

```
POST /api/v1/sauvegardes/{id}/verification
```

Chaque empreinte du manifeste est recalculée. Toute divergence est listée dans
`mismatched` et la sauvegarde est refusée pour restauration.

## 4. Restaurer — toujours sur copie

```
POST /api/v1/sauvegardes/restauration
{ "archive_path": "…/sauvegarde-20260801-120000.zip",
  "destination":  "C:\\CommissionMSI\\restauration-test" }
```

Règles appliquées :

1. L'intégrité est vérifiée **avant** toute écriture.
2. Le répertoire de destination doit être **vide**. Aucune donnée existante
   n'est jamais écrasée automatiquement.
3. En cas d'échec, rien n'est écrit et l'installation d'origine reste intacte.
4. Une clé incorrecte fait échouer le déchiffrement de manière explicite.

## 5. Remise en service après restauration

1. Vérifiez la copie restaurée : ouvrez quelques dossiers, contrôlez les
   empreintes SHA-256 et la lisibilité des textes.
2. Arrêtez l'application.
3. Remplacez manuellement le répertoire `data/` par la copie validée.
4. Relancez et vérifiez `GET /api/v1/readiness` puis `GET /api/v1/diagnostic`.

## 6. Recommandations

- Testez la restauration **avant** tout usage réel, sur une copie.
- Conservez au moins deux générations de sauvegardes sur supports distincts.
- Ne stockez jamais une sauvegarde sur un service cloud non autorisé.
- Après toute perte de `master.key`, les données chiffrées sont irrécupérables :
  il n'existe aucune porte dérobée.
