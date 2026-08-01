# Sécurité

*Designed by Prof. Merzoug Mohamed.*

## 1. Modèle de menace assumé

L'application n'a **aucun compte, aucun mot de passe, aucune session**. La
protection repose entièrement sur :

- l'isolement local : écoute exclusive sur `127.0.0.1` ;
- le chiffrement complet du disque (BitLocker recommandé) ;
- les permissions de fichiers du poste Windows ;
- l'absence totale d'exposition réseau entrante.

Toute personne ayant un accès interactif au poste déverrouillé a accès aux
dossiers. C'est une limite acceptée et documentée, non un défaut caché.

## 2. Écoute et origine

| Contrôle | Mise en œuvre |
|---|---|
| Écoute locale | `MSI_HOST=127.0.0.1` ; le lanceur refuse toute autre adresse |
| En-tête `Host` | Rejeté s'il n'est pas une adresse de bouclage (403) |
| `Origin` | Rejeté s'il n'est pas local (403) |
| `Referer` | Rejeté sur méthode mutante si non local (403) |
| Adresse distante | Uniquement via `MSI_ALLOW_REMOTE=true`, avec avertissement |

Aucune route `/setup`, `/login` ou `/logout` n'existe. Toute route d'API
inconnue répond `404` quelle que soit la méthode HTTP.

## 3. En-têtes de réponse

```
Content-Security-Policy: default-src 'self'; script-src 'self';
  style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
  font-src 'self'; connect-src 'self'; object-src 'none';
  frame-ancestors 'none'; base-uri 'self'; form-action 'self'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Cache-Control: no-store
```

`connect-src 'self'` interdit au navigateur tout appel sortant : la recherche
en ligne passe exclusivement par le backend, sous politique de liste blanche.

## 4. Chiffrement

- **AES-256-GCM** pour les documents, textes de pages, extraits, commentaires,
  corrections, notes, justifications et résultats de recherche.
- **AAD liée à l'identifiant logique** (`page:<id>:original`,
  `document:<id>`, `claim:<id>:statement`…). Une AAD incorrecte fait échouer le
  déchiffrement : un blob ne peut pas être substitué à un autre.
- `master.key` : 32 octets, créée avec `O_EXCL` et permissions `0600`, jamais
  régénérée si le fichier existe.
- **Perdre `master.key` rend les données chiffrées définitivement illisibles.**

Limite documentée : les métadonnées minimales de recherche locale (référence,
intitulé, organisateur, statut, numéros de page, empreintes) restent en clair
dans la base afin de permettre le filtrage et le tri.

## 5. Politique de sortie réseau

Le cœur documentaire — import, OCR, saisie, contrôles, grille, rapports — est
**entièrement hors ligne**. Seul le module de recherche contrôlée émet des
appels sortants, sous quatre verrous cumulatifs :

1. **Interrupteur général** `MSI_NETWORK_DISABLED=true` coupe immédiatement
   tout accès externe sans arrêter l'application.
2. **Liste blanche de domaines** (`MSI_ALLOWED_DOMAINS`), vérifiée avant chaque
   appel ; tout autre domaine est refusé et journalisé.
3. **TLS obligatoire** : seules les URL `https://` sont autorisées.
4. **Garde-fou de contenu** (`web_research/redaction.py`) : la requête est
   refusée si elle contient un PDF, une référence à un document d'identité, un
   courriel, un numéro de téléphone, une donnée d'état civil, une coordonnée
   bancaire, une référence interne de dossier ou une mention de note interne.
   Elle doit tenir sur une ligne et rester sous 300 caractères.

Aucun PDF, aucune pièce, aucun document d'identité et aucune note interne ne
quitte jamais le poste. Chaque requête est relue, modifiable et explicitement
approuvée par l'évaluateur avant envoi.

Les clés API éventuelles sont lues uniquement dans l'environnement local. Elles
n'apparaissent jamais dans le code, les journaux, les réponses de l'API ou les
sauvegardes.

## 6. Import de fichiers

- Vérification de l'en-tête `%PDF-`, de la structure et de l'ouverture réelle.
- Refus explicite : fichier vide, faux PDF, corrompu, protégé par mot de passe,
  au-delà de `MSI_MAX_UPLOAD_MB`.
- **Aucun résultat partiel** n'est jamais présenté comme valide après un refus.
- Noms de fichiers neutralisés (`safe_filename`) : séparateurs, `..`,
  caractères de contrôle et noms réservés Windows (`CON`, `PRN`, `LPT1`…).
- Tous les chemins sont résolus sous leur racine autorisée (`resolve_within`).
- Fichiers temporaires dans un répertoire dédié, supprimé après usage.

## 7. Transactions

Toute écriture SQLite est validée par un `commit()` explicite **avant** qu'un
succès soit renvoyé. En cas d'échec, `rollback()` restaure l'état précédent :
aucune demi-validation, aucun résultat partiel présenté comme valide.

## 8. Journal d'audit

Le journal enregistre démarrage/arrêt, contrôles de santé, imports, empreintes,
analyses, consultations d'originaux, OCR et confiance, corrections,
confirmations, rejets, modifications de pièces, notes, qualifications
d'alertes, connectivité, requêtes Web, fournisseurs appelés, erreurs réseau,
sources consultées, affirmations, homonymies, exécutions d'agents, désaccords,
ranking, conclusions, rapports, sauvegardes, restaurations et changements de
règles.

Les valeurs sensibles n'y figurent **jamais en clair** : seules des empreintes
`sha256:…`. Une correction ne supprime jamais la valeur initiale.

## 9. Données restreintes

Les documents d'identité et listes de passeports portent la sensibilité
`RESTREINT` : leurs extraits sont masqués dans les écrans et exports
ordinaires, et chaque accès à l'original est tracé par un événement
`RESTRICTED_ACCESS` distinct.

## 10. Rappels d'exploitation

- Ne perdez jamais `data/master.key`.
- Activez BitLocker : le chiffrement applicatif ne remplace pas le chiffrement
  complet du disque.
- N'exposez jamais l'application au réseau.
- Une sauvegarde contient `master.key` : conservez-la sur support chiffré.
- Conservez les dossiers réels hors de tout service cloud non autorisé.
- Vérifiez les conditions d'utilisation de chaque fournisseur avant de
  l'ajouter à la liste blanche.
