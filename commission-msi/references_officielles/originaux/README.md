# Originaux officiels — emplacement réservé

Ce dossier est **volontairement vide dans le dépôt**. Les cinq documents
officiels ne sont pas versionnés : ils appartiennent à l'institution et ne
doivent pas circuler dans un dépôt de code.

## Fichiers attendus

Déposez ici les cinq originaux du kit, sans les renommer :

| Fichier | SHA-256 attendu |
|---|---|
| `Manuel_procedures_commission_manifestations_scientifiques_internationales.docx` | `b488d5bd027a68178f96b110ecdaa99fe3370b79c92a5939069491f89ee053fe` |
| `Envoi_595-SG_19-5-2025_Organisation_manifestations_scientifiques.pdf` | `43b3953a43fe03ea486bafaa235e9626c56caa60b9c7b2e09fd2798becfd2760` |
| `Guide_Manifestations_internationales.doc` | `1213d761cd34469a9066bda6bb4ec9865b00887e48ed19277e39cf33493d44cf` |
| `Dossier_demande_organisation_manifestation_internationale.pdf` | `e41641703aa07bd17f3a052d9819ae9c3e6b47e1efd42ba7a686d3cca676412e` |
| `Envoi_218-DCEU-SDPUR_14-7-2026_الاجراءات_التظاهرات_العلمية.pdf` | `9ae95d6bc805e8e2f11f1ceef9c087bbcffa9b63ad356476047714975dfc5cbe` |

Les empreintes proviennent de `../donnees/manifest_sources.json`, qui fait
foi.

## Contrôle d'intégrité (porte G0_SOURCE)

```bash
python scripts/verify_sources.py
```

Le script recalcule l'empreinte de chaque original présent et la compare au
manifeste. Une empreinte divergente **suspend toutes les règles normatives
liées** jusqu'à revalidation humaine ; une source absente reste marquée
`NON_PRESENTE` et ne peut activer aucune règle normative.

Les originaux prévalent toujours sur les extractions Markdown de
`../extractions/`, qui servent uniquement d'index de recherche.

---

*Designed by Prof. Merzoug Mohamed — Conçu par le Professeur Merzoug Mohamed.*
