# Audit du système Fleet Tracker — 2.0.0

Date de mise à jour : 13 octobre 2026. Branche observée : `docs/report-react-frontend`. Vérification documentaire du tree courant ; aucune connexion base, lecture `.env`, ni essai téléphone n'a été effectué pour cette mise à jour. Les résultats d'exécution explicitement fournis par le propriétaire sont étiquetés « rapporté par le propriétaire » et ne sont pas présentés comme vérifiés par l'auditeur. Les valeurs sensibles sont omises.

## Méthode et niveaux de preuve

- **VERIFIED** : directement visible dans le code ou reproduit par une commande exécutée durant cet audit.
- **INFERRED** : conclusion tirée du code, du manifeste suivi ou d'une absence recherchée ; ce n'est pas une observation d'exécution.
- **UNKNOWN / UNVERIFIED** : nécessite l'accès à une machine, une base, un compte, un équipement ou un environnement non disponible.
- Les références `fichier:ligne` pointent vers le code suivi. Pour l'état réel de la base et du matériel, une définition de schéma ou un test mocké ne vaut pas vérification en production.

L'arborescence actuelle contient les migrations `0001_initial_schema.py` à `0006_vehicle_tenant_uniqueness.py` (**VERIFIED** par `backend/alembic/versions/`). Le propriétaire rapporte que les migrations 0005 et 0006 ont été appliquées; l'état de la base n'a pas été contrôlé indépendamment (**rapporté par le propriétaire / non vérifié par l'auditeur**). Les octets ou contenus d'un fichier local ignoré (notamment `.env`) n'ont pas été lus.

## 1. Inventaire des composants et capacités

| Composant/capacité | État | Preuve |
|---|---|---|
| API FastAPI asynchrone, accès PostgreSQL/SQLAlchemy | IMPLEMENTED | `backend/main.py:1-114`; `backend/app/db.py:1-13`; `backend/requirements.txt:1-11` (**VERIFIED**) |
| Frontend Web | IMPLEMENTED | React 19.3.0, TypeScript 6.0.3, Vite 8.3.4, Vitest 5.0.4, ESLint 10.12.0 et Leaflet 1.9.4 via npm; trois entrées HTML (`index.html`, `platform.html`, `invite.html`) configurées dans `frontend/vite.config.ts`, avec bundles de page et chunk partagé (**VERIFIED**) |
| Tableau de bord admin | IMPLEMENTED | `frontend/index.html`; entrée React `frontend/src/main.tsx`; carte Leaflet importée de npm (`frontend/src/dashboard/MapView.tsx`) (**VERIFIED**) |
| Console opérateur de plateforme | IMPLEMENTED | `frontend/platform.html`; entrée React `frontend/src/platform.tsx`; routes `backend/app/platform/router.py:154-490` (**VERIFIED**) |
| Page publique d'acceptation d'invitation | IMPLEMENTED | `frontend/invite.html`; entrée React `frontend/src/invite.tsx`; `backend/app/platform/invitations.py:145-191` (**VERIFIED**) |
| Application mobile chauffeur Android/iOS | PARTIAL : queue persistante, batch et service foreground Android dans le code; appareil non vérifié | `queue.ts:1-90`, `tracker.ts:93-194,220-330`, `MainScreen.tsx:17-155`; le chemin iOS ne démarre pas le service Android. GPS, permissions et comportement suspendu/arrière-plan restent **UNVERIFIED** (**VERIFIED code; device UNKNOWN**) |
| Dispatch, attribution de courses, ERP, fonctions ML | NOT IMPLEMENTED | Le README les place dans les phases futures (`./README.md:3`, `./README.md:167`) (**VERIFIED**) |
| PostgreSQL de développement sous Compose | PARTIAL | Seul le service `postgres` est défini, pas de service backend/frontend (`backend/docker-compose.yml:1-15`) (**VERIFIED**) |
| CI, registre d'images, déploiement staging/production, monitoring | NOT IMPLEMENTED dans le dépôt suivi | L'inventaire `git ls-files` ne contient ni pipeline CI ni manifeste de déploiement/monitoring ; README indique explicitement qu'ils sont différés (`./README.md:48-55`, `./README.md:167`) (**INFERRED**) |
| Sauvegarde et test de restauration PostgreSQL | IMPLEMENTED comme scripts locaux; le propriétaire rapporte restore PASS pour les cinq tables comparées | `scripts/backup/backup-db.ps1:1-208`; `scripts/backup/restore-test.ps1:1-200` (**scripts vérifiés; exécution rapportée par le propriétaire**) |
| Tâche quotidienne Windows de sauvegarde | PARTIAL : inscription manuelle possible | `scripts/backup/register-backup-task.ps1:1-42`; script inscrit une tâche « FleetBackup », mais son existence sur une machine est inconnue (**VERIFIED / UNKNOWN**) |
| Tâches locales accessibles via console | PARTIAL et désactivé par défaut | `backend/main.py:70-109`; `backend/app/platform/devtasks/tasks.py:25-149`; la valeur d'exemple `DEV_TASKS_ENABLED` est désactivée (`.env.example:1-6`) (**VERIFIED**) |

### Routes HTTP/WebSocket

« Session admin » désigne le cookie `admin_session`, « session plateforme » le cookie indépendant `platform_session`, « jeton chauffeur » l'en-tête `X-Token`. La page d'acceptation est publique et son jeton est reçu dans le corps. Les routes Dev n'existent que si le drapeau est activé. (**VERIFIED** — `backend/main.py:92-109`, `281-363`, `431-752`; `backend/app/platform/router.py:154-490`; `backend/app/platform/invitations.py:161-191`; `backend/app/platform/devtasks/router.py:176-265`)

| Méthode / chemin | Authentification | Fonction | État |
|---|---|---|---|
| `POST /admin/login` | Identifiants admin | Ouvre une session admin | IMPLEMENTED |
| `POST /admin/logout` | Cookie admin facultatif pour révocation | Révoque et efface le cookie | IMPLEMENTED |
| `GET /admin/me` | Session admin | Identité et centre | IMPLEMENTED |
| `GET /admin/admins` | Session admin | Liste bornée/paginée des admins du centre | IMPLEMENTED |
| `POST /admin/admins/{admin_id}/deactivate` | Session admin | Désactive un admin du centre, protège l'acteur et le dernier admin actif | IMPLEMENTED |
| `POST /admin/drivers` | Session admin | Crée chauffeur/véhicule, renvoie le jeton chauffeur une fois | IMPLEMENTED |
| `PATCH /admin/drivers/{driver_id}` | Session admin | Modifie chauffeur/véhicule | IMPLEMENTED |
| `GET /admin/drivers/latest` | Session admin, `limit` 1–1000 | Chauffeurs et dernières positions du centre | IMPLEMENTED |
| `POST /admin/drivers/{driver_id}/deactivate` | Session admin | Désactive et invalide le jeton courant | IMPLEMENTED |
| `POST /admin/drivers/{driver_id}/reactivate` | Session admin | Réactive et renvoie un nouveau jeton | IMPLEMENTED |
| `POST /admin/drivers/{driver_id}/token` | Session admin | Renouvelle le jeton actif | IMPLEMENTED |
| `POST /status` | Jeton chauffeur `X-Token` | Modifie l'état en ligne | IMPLEMENTED |
| `POST /location` | Jeton chauffeur `X-Token` | Valide, enregistre et diffuse une position | IMPLEMENTED |
| `POST /location/batch` | Jeton chauffeur `X-Token` | Valide un lot borné, rapporte acceptés/doublons/rejets et diffuse le point le plus récent accepté | IMPLEMENTED |
| `WS /ws` | Cookie admin et vérification Origin/Host | Flux réservé au centre de l'admin | IMPLEMENTED |
| `POST /platform/login` | Identifiants super-admin | Ouvre une session plateforme | IMPLEMENTED |
| `POST /platform/logout` | Session plateforme | Révoque et efface le cookie plateforme | IMPLEMENTED |
| `GET /platform/me` | Session plateforme | Identité super-admin | IMPLEMENTED |
| `GET /platform/centers` | Session plateforme, pagination | Liste les centres et agrège des compteurs | IMPLEMENTED |
| `POST /platform/centers` | Session plateforme | Crée un centre | IMPLEMENTED |
| `POST /platform/centers/{center_id}/invitations` | Session plateforme | Crée une invitation | IMPLEMENTED |
| `GET /platform/centers/{center_id}/invitations` | Session plateforme, pagination | Liste les invitations du centre demandé | IMPLEMENTED |
| `POST /platform/invitations/{invitation_id}/revoke` | Session plateforme | Révoque une invitation | IMPLEMENTED |
| `GET /platform/audit` | Session plateforme, pagination | Liste les événements d'audit plateforme | IMPLEMENTED |
| `POST /invitations/accept` | Public, jeton à usage unique dans le corps | Accepte l'invitation et crée l'admin | IMPLEMENTED |
| `GET /platform/dev/tasks`, `POST /platform/dev/tasks/{task_id}/run`, `POST /platform/dev/runs/{run_id}/stop`, `GET /platform/dev/runs`, `GET /platform/dev/runs/{run_id}` | Super-admin plateforme, client loopback et optionnellement Origin autorisé | Tâches locales allowlistées | PARTIAL, optionnel |

Preuve des verbes/chemins : `backend/main.py:519-1195`, `backend/app/platform/router.py:154-490`, `backend/app/platform/invitations.py:171-191`, `backend/app/platform/devtasks/router.py:176-273`. Les limites de liste sont visibles dans `backend/main.py:601-618,827-840`, `backend/app/platform/router.py:252-258,372-380,457-464` et `backend/app/platform/devtasks/router.py:239-273`.

### Pages, écrans, scripts et tâches

- Pages web : tableau de bord (`frontend/index.html`), console plateforme (`frontend/platform.html`), acceptation invitation (`frontend/invite.html`) — **IMPLEMENTED**; React/TypeScript et Vite configurent trois entrées de build (`frontend/vite.config.ts`).
- Écrans mobiles : `TokenEntryScreen`, `MainScreen`, `SettingsScreen` — **IMPLEMENTED** ; démarrage app avec token enregistré (`DriverApp/App.tsx:1-86`; `TokenEntryScreen.tsx:1-127`; `MainScreen.tsx:1-239`; `SettingsScreen.tsx:1-130`). Suivi, file persistante et envoi par lot existent dans le code; le comportement sur téléphone reste **UNVERIFIED**.
- Scripts backend : semer le centre par défaut, créer admin, créer premier super-admin, désactiver admin — **IMPLEMENTED** (`backend/scripts/seed_default_center.py:1-38`; `seed_admin.py:1-115`; `seed_super_admin.py:1-108`; `deactivate_admin.py:1-93`).
- Scripts backup : `backup-db.ps1:1-208`, `restore-test.ps1:1-200`, `register-backup-task.ps1:1-42` — **IMPLEMENTED comme outils opérateur**, aucun résultat d'exécution réelle n'a été vérifié.
- Tâches prédéfinies du lanceur : démarrer PostgreSQL local, état Docker, backup, test de restore, état/upgrade Alembic, tests backend et serveur de développement Vite — **IMPLEMENTED comme catalogue facultatif** (`backend/app/platform/devtasks/tasks.py:25-149`). La tâche `frontend_serve` lance `npm.cmd run dev` et ne fonctionne donc que sous Windows.
- Job planifié applicatif : aucun job de fond applicatif identifié ; sauvegarde Windows quotidienne installable manuellement seulement. État effectif de planification : **UNKNOWN** (`scripts/backup/register-backup-task.ps1:1-42`).

## 2. Modèle de données

Tous les identifiants primaires sont des UUID. Les colonnes et relations ci-dessous sont les modèles présents dans `backend/app/models.py`; les révisions indiquent la création ou l'évolution suivie (`backend/alembic/versions/0001_initial_schema.py:18-133`, `0002_admin_sessions.py:17-56`, `0003_platform_console.py:16-107`, `0004_admin_invitations.py:16-59`, `0005_location_dedup.py:1-45`, `0006_vehicle_tenant_uniqueness.py:1-150`). **L'état de la base réellement appliqué est rapporté par le propriétaire, non vérifié indépendamment.**

| Table (révision) | Colonnes métier (en sus de `id`) | Clés, contraintes et index principaux |
|---|---|---|
| `centers` (0001) | `name`, `city`, `timezone`, `active`, `created_at`, `deactivated_at` | PK `id`; parents des admins, chauffeurs, zones, journaux |
| `super_admins` (0001) | `email`, `password_hash`, `created_at`, `last_login`, `active` | PK; unicité email et index unique fonctionnel `lower(email)` (0003); pas de centre associé |
| `admins` (0001; modifié 0002) | `center_id`, `email`, `password_hash`, `role`, `active`, `created_at`, `deactivated_at`, `last_login` | FK centre; email unique global, check email minuscule; index centre; l'ancienne unicité centre/email et index email ont été remplacés en 0002 |
| `drivers` (0001) | `center_id`, `name`, `phone`, `token_hash`, `active`, `online`, `created_at`, `deactivated_at` | FK centre; token hash unique; index centre |
| `vehicles` (0001; `center_id` et unicité tenant en 0006) | `center_id`, `driver_id`, `taxi_number`, `plate_number`, `type`, `active`, `created_at`, `deactivated_at` | FK centre et chauffeur; `driver_id` unique/indexé; UNIQUE `(center_id, taxi_number)` et `(center_id, plate_number)`; index centre et taxi |
| `driver_locations` (0001; déduplication en 0005) | `center_id`, `driver_id`, `lat`, `lng`, `speed`, `heading`, `accuracy`, `recorded_at` | FK centre et chauffeur; UNIQUE `(driver_id, recorded_at)`; index centre, chauffeur et date |
| `driver_status_logs` (0001) | `driver_id`, `online`, `changed_at` | FK chauffeur; index chauffeur et date |
| `zones` (0001) | `center_id`, `code`, `name`, `boundary` | FK centre; unique `(center_id, code)`; index centre |
| `audit_logs` (0001) | `center_id`, `actor_admin_id`, `action`, `entity_type`, `entity_id`, `before_state`, `after_state`, `created_at` | FK centre/admin; index centre, acteur, type, identifiant d'entité, date; états JSONB |
| `admin_sessions` (0002) | `admin_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at` | FK admin; index unique hash, index admin |
| `platform_sessions` (0003) | `super_admin_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at` | FK super-admin; index unique hash, index super-admin |
| `platform_audit_log` (0003) | `super_admin_id`, `action`, `target_type`, `target_id`, `ip`, `user_agent`, `success`, `created_at`, `email_hash` | FK super-admin nullable; index date et super-admin |
| `admin_invitations` (0004) | `center_id`, `email`, `token_hash`, `created_at`, `expires_at`, `used_at`, `revoked_at`, `created_by_super_admin_id` | FK centre et super-admin nullable; check email minuscule; index centre, index unique hash |

Sources détaillées des champs : `backend/app/models.py:20-237`. Détails DDL/contraintes et indexes : `0001_initial_schema.py:18-133`; session/email admin : `0002_admin_sessions.py:17-56`; sessions/journal plateforme : `0003_platform_console.py:16-107`; invitations : `0004_admin_invitations.py:16-59`; unicité des positions : `0005_location_dedup.py:1-45`; colonne centre et unicité tenant véhicules : `0006_vehicle_tenant_uniqueness.py:1-150`.

**Inventaire explicite des contraintes et indexes déclarés** (`0001_initial_schema.py:18-133`; `0002_admin_sessions.py:17-56`; `0003_platform_console.py:16-107`; `0004_admin_invitations.py:16-59`; `0005_location_dedup.py:1-45`; `0006_vehicle_tenant_uniqueness.py:1-150`; modèles `backend/app/models.py:20-237`):

| Table | PK/FK/UNIQUE/CHECK | Indexes nommés |
|---|---|---|
| `centers` | PK `id` | Aucun index secondaire déclaré |
| `super_admins` | PK `id`; email unique | `uq_super_admin_email_lower` unique sur `lower(email)` (0003) |
| `admins` | PK `id`; FK `center_id`; unique global `uq_admin_email`; check `ck_admin_email_lowercase`; unicité initiale `uq_admin_center_email` retirée en 0002 | `ix_admins_center_id`; `ix_admins_email` initial supprimé en 0002 |
| `drivers` | PK `id`; FK centre; unique `token_hash` | `ix_drivers_center_id` |
| `vehicles` | PK `id`; FK `center_id`, `driver_id`; unique `driver_id`; unique `(center_id, taxi_number)` et `(center_id, plate_number)` | `ix_vehicles_driver_id`; `ix_vehicles_taxi_number`; `ix_vehicles_center_id` (0006) |
| `driver_locations` | PK `id`; FK centre et chauffeur; UNIQUE `(driver_id, recorded_at)` (0005) | `ix_driver_locations_center_id`; `ix_driver_locations_driver_id`; `ix_driver_locations_recorded_at`; indexes déclarés initialement dont `ix_driver_locations_driver_recorded` |
| `driver_status_logs` | PK `id`; FK chauffeur | `ix_driver_status_logs_driver_id`; `ix_driver_status_logs_changed_at` |
| `zones` | PK `id`; FK centre; unique `(center_id, code)` nommée `uq_zone_center_code` | `ix_zones_center_id` |
| `audit_logs` | PK `id`; FK centre et admin acteur | `ix_audit_logs_center_id`; `ix_audit_logs_actor_admin_id`; `ix_audit_logs_entity_type`; `ix_audit_logs_entity_id`; `ix_audit_logs_created_at` |
| `admin_sessions` | PK `id`; FK admin | `ix_admin_sessions_token_hash` unique; `ix_admin_sessions_admin_id` |
| `platform_sessions` | PK `id`; FK super-admin | `ix_platform_sessions_token_hash` unique; `ix_platform_sessions_super_admin_id` |
| `platform_audit_log` | PK `id`; FK nullable super-admin | `ix_platform_audit_log_created_at`; `ix_platform_audit_log_super_admin_id` |
| `admin_invitations` | PK `id`; FK centre et super-admin créateur nullable; check email minuscule `ck_admin_invitations_email_lowercase` | `ix_admin_invitations_center_id`; `ix_admin_invitations_token_hash` unique |

Cette description reflète les modèles et migrations suivis, pas une introspection directe de PostgreSQL. L'application des migrations 0005 et 0006 est **rapportée par le propriétaire**, sans vérification indépendante.

**Usage des tables** :

- `centers`, `admins`, `super_admins`, `drivers`, `vehicles`, `driver_locations`, `audit_logs`, `admin_sessions`, `platform_sessions`, `platform_audit_log`, `admin_invitations` ont des références d'exécution dans les routes, scripts ou authentifications (`backend/main.py`; `backend/app/platform/router.py`; `backend/app/platform/auth.py`; `backend/app/platform/invitations.py`; `backend/app/platform/audit.py`; `backend/scripts/`). **VERIFIED**.
- `zones` n'a, parmi le code Python suivi, qu'un modèle et une relation SQLAlchemy, pas de route de gestion identifiée : table non utilisée par le parcours applicatif actuel (**INFERRED**, `backend/app/models.py:29-30,229-237`; routes inventoriées plus haut).
- `driver_status_logs` n'a, parmi le code Python suivi, qu'un modèle/relation, et aucun ajout d'événement de statut dans `/status` ou `/location` : table apparemment inutilisée (**INFERRED**, `backend/app/models.py:188-191,220-227`; `backend/main.py:684-749`).
- `vehicles.active` et `vehicles.deactivated_at` existent en schéma mais le code de gestion met à jour le véhicule sans exploiter ces champs : potentiellement non utilisés (**INFERRED**, `backend/app/models.py:193-204`; `backend/main.py:484-525`).
- `super_admins` n'est pas inutilisée : authentification et console s'en servent ; `last_login` est mis à jour à la connexion plateforme. `admins.last_login` est présent, mais aucune mise à jour à la connexion admin n'a été repérée (**VERIFIED / INFERRED**, `backend/app/platform/router.py:162-204`; `backend/main.py:281-318`; modèles `backend/app/models.py:35-73`).
- `vehicles.center_id` est une FK/index non nullable; taxi et plaque sont uniques par centre. La migration 0006 retire l'unicité globale du taxi et vérifie les doublons avant l'ajout des contraintes (`backend/alembic/versions/0006_vehicle_tenant_uniqueness.py:34-107`; `backend/app/models.py:193-216`). Migration appliquée : **rapporté par le propriétaire**, non vérifié directement.

## 3. Parcours logiques

### Authentification chauffeur

1. L'admin crée un chauffeur dans son centre ; le serveur génère un token aléatoire `secrets.token_urlsafe`, stocke son SHA-256 et ne renvoie la valeur brute qu'à la création (`backend/main.py:431-481`).
2. L'app stocke le token dans AsyncStorage puis l'ajoute en `x-token` aux POST statut/position (`DriverApp/src/screens/TokenEntryScreen.tsx:19-38`; `DriverApp/src/api/client.ts:32-63`).
3. L'API hache le token reçu, cherche un chauffeur actif et dérive centre et identité de la ligne trouvée (`backend/main.py:363-377`).
4. Désactivation remplace le hash par un hash d'un nouveau token jeté, désactive le chauffeur et l'annonce hors ligne. Réactivation/régénération renvoie un nouveau token et l'ancien ne correspond plus (`backend/main.py:618-682`).

Ce parcours est **IMPLEMENTED**. Stockage AsyncStorage et transport HTTP clair dans les valeurs par défaut de développement sont des limites de protection (`DriverApp/src/api/client.ts:33-58`; `DriverApp/docs/TECHNICAL_DECISIONS.md:1-16`; l'URL frontend par défaut est définie dans `frontend/src/api/client.ts`).

### Connexion admin et plateforme

1. L'admin est identifié par email normalisé et mot de passe Argon2; un hash factice est vérifié quand l'adresse n'existe pas. Le succès crée une session de huit heures, hashée en base, envoyée dans cookie HTTP-only, SameSite Strict; Secure dépend de `APP_ENV` (`backend/main.py:43-44,208-218,281-318`).
2. Le contrôle de session valide hash, révocation, échéance et état actif du compte (`backend/main.py:222-257`).
3. La plateforme a un cookie distinct `platform_session`, une table/session d'identité distincte, une durée de quatre heures et un chemin `/platform`; les routes privées dépendent de `require_super_admin` (`backend/app/platform/auth.py:14-65`; `backend/app/platform/router.py:154-245`).
4. Tests vérifient que les cookies ne sont pas interchangeables ni utilisés pour le WebSocket (`backend/tests/test_platform.py:136-160`).

L'isolation admin/plateforme est **VERIFIED dans le code et testée avec clients de test**, mais pas testée en conditions réelles sur un serveur configuré.

### WebSocket et diffusion

1. `/ws` refuse l'Origin s'il ne figure pas dans l'allowlist et ne correspond pas au Host, exige le cookie admin et revalide sa session.
2. Le socket est associé au `center_id` de l'admin issu de cette session.
3. `broadcast` choisit uniquement les sockets enregistrés avec le centre fourni; il supprime un socket en échec ou après deux secondes.
4. Seuls changement de statut, passage automatique en ligne lors de la première position, position acceptée et désactivation diffusent des événements.

Preuve : `backend/main.py:259-279,379-393,618-644,684-749,751-777`. Implémentation **VERIFIED** ; réseau multi-processus, reconnexion utilisateur réel et charge **UNKNOWN** (registry en mémoire du processus).

### Ingestion de position et déduplication

1. `Loc` et `LocationBatch` appliquent des modèles stricts; un lot contient 1 à 50 points et le middleware limite la taille de corps (`backend/main.py:208-239,421-440`).
2. Le token doit désigner un chauffeur actif. Validation rejette coordonnées hors limites, champs cap/vitesse/précision invalides, date trop future/ancienne, points trop fréquents et déplacement invraisemblable (`backend/app/locations.py:37-80`; seuils de configuration `backend/app/config.py:28-66`).
3. `/location` traite un point; `/location/batch` trie les points par date, vérifie les doublons, valide les points et répond avec les compteurs acceptés/doublons/rejetés et les index de rejet (`backend/main.py:1005-1087,1089-1191`).
4. La base impose l'unicité chauffeur/horodatage (migration 0005); insertion en transaction. Si un point accepté est plus récent que le dernier connu, le serveur diffuse seulement ce point le plus récent au centre du chauffeur; le statut passe en ligne si nécessaire.

L'ingestion simple et par lots est **IMPLEMENTED**. Le détail d'application des migrations 0005 et 0006 est rapporté par le propriétaire, mais non interrogé par l'auditeur.

### Mobile, file hors ligne et service en arrière-plan

L'application persiste une file locale AsyncStorage bornée à 1 000 positions, trie les points chronologiquement, envoie des lots jusqu'à 50 et applique un backoff avec jitter aux erreurs réseau (`DriverApp/src/location/queue.ts:1-90`; `DriverApp/src/location/tracker.ts:93-194`). Les réponses valides font acquitter acceptés/doublons et retirer les rejets. Android utilise `react-native-background-actions` avec un service foreground de type location; le chemin iOS démarre le watcher sans ce service Android (`DriverApp/src/location/tracker.ts:14-24,220-330`). MainScreen restaure le statut/file et demande les autorisations prévues (`DriverApp/src/screens/MainScreen.tsx:17-82,100-155`). **Comportement réel GPS, permissions, poursuite écran verrouillé/arrière-plan et fiabilité sur appareil : UNVERIFIED; aucun téléphone n'a été testé par l'auditeur.**

### Invitations et gestion

- Super-admin crée une invitation limitée à un centre actif, révoque les anciennes invitations inutilisées au même centre/adresse, fabrique un jeton aléatoire et conserve son hash. Le token est rendu une seule fois et la réponse `no-store`; expiration prévue à 48 h (`backend/app/platform/invitations.py:41-88`; `backend/app/platform/router.py:324-370`).
- L'acceptation réclame atomiquement l'invitation non consommée, non révoquée et non expirée; crée un admin dans le centre lié, hash Argon2 du mot de passe et journalise l'événement dans la transaction (`backend/app/platform/invitations.py:90-141,172-191`).
- Les opérations de chauffeur sélectionnent le centre depuis la session admin; accès à un identifiant hors centre est traité comme absent. Les ajouts/modifications journalisent certaines actions; erreurs d'unicité sont rollback et HTTP 409 (`backend/main.py:395-429,431-525`; tests `backend/tests/test_admin_auth.py:657-935`).
- Le seed initial du centre choisit n'importe quel premier centre selon une requête avec `limit(1)` et crée un centre par défaut seulement si la table est vide; le seed admin requiert un seul centre ou un UUID explicite (`backend/scripts/seed_default_center.py:14-28`; `backend/scripts/seed_admin.py:35-82`).

### Backups, restauration et lanceur dev

- `backup-db.ps1` crée un dump PostgreSQL custom-format dans un dossier extérieur au dépôt, vérifie qu'il est listable, copie et checksum SHA-256, conserve 14 backups récents plus jusqu'à 8 sauvegardes du dimanche; le paramètre `-WhatIf` prévisualise seulement les suppressions de rétention, pas la création du backup (`scripts/backup/backup-db.ps1:42-116,122-208`).
- `restore-test.ps1` restaure dans la base fixe `fleet_restore_test`, compare les comptages de `drivers`, `driver_locations`, `admins`, `centers` et `vehicles`, puis nettoie la base temporaire; seule la table positions peut avoir une tolérance. C'est une vérification de restauration partielle par comptage, pas une validation de toutes les données applicatives (`scripts/backup/restore-test.ps1:8-10,100-200`).
- Le propriétaire rapporte que son test de restauration a affiché **PASS pour les cinq tables**. Ce résultat n'a pas été reproduit ni vérifié par l'auditeur; les scripts présents et leur logique sont **VERIFIED dans le tree**, l'exécution est **rapportée par le propriétaire**.
- Existence, contenu, protection/copie indépendante des fichiers de sauvegarde et tâche Windows effectivement enregistrée sur la machine : **UNKNOWN** faute d'inspection de l'environnement.
- `DEV_TASKS_ENABLED` désactivé par défaut; activé implique WARNING au démarrage et refus en production (`backend/main.py:70-88,92-109`). Liste de commandes fixe; endpoints exigent super-admin et boucle locale; runs sont gardés en mémoire et sortie bornée à 500 lignes (`backend/app/platform/devtasks/tasks.py:25-149`; `backend/app/platform/devtasks/router.py:56-103,176-273`; `backend/app/platform/devtasks/runner.py:22-50,112-314`). Une tâche one-shot déjà définie lance `docker compose up -d` sans spécifier le service alors que le manifeste Compose ne contient que PostgreSQL : effet réel dépend du contexte Compose; à vérifier (`backend/app/platform/devtasks/tasks.py:25-38`; `backend/docker-compose.yml:1-15`).

## 4. Isolation entre centres

**Revue du code observé — pas audit live de données.**

| Requête/opération | Cloisonnement observé |
|---|---|
| Auth admin / sessions | La recherche d'admin est globale par email (identité globale); validation session charge l'admin actif. Aucun contenu d'un autre centre n'est renvoyé par ces routes d'identité (`backend/main.py:222-318`). |
| Chauffeur via `X-Token` | Requête par hash unique et actif, puis centre dérivé du chauffeur; aucune valeur centre fournie par le client (`backend/main.py:363-377`). |
| Liste chauffeurs/dernières positions | Filtre `DriverLocation.center_id` et `Driver.center_id` à l'ID admin session; le véhicule joint par `driver_id` d'un chauffeur déjà filtré (`backend/main.py:526-615`). |
| Lecture/modification d'un chauffeur par ID | Condition `Driver.id` **et** `Driver.center_id == admin.center_id` (`backend/main.py:417-429,484-525,618-682`). |
| Création chauffeur et journal associé | Centre dérivé de l'admin vérifié (`backend/main.py:431-481,407-415`). |
| Statut/position/broadcast chauffeur | Centre dérivé du chauffeur authentifié; broadcast utilise ce centre (`backend/main.py:684-749`). |
| Sockets admin | Centre issu de session validée, conservé dans registry, recipients filtrés par centre (`backend/main.py:379-393,751-777`). |
| Invitations par centre | Création/listing filtre le centre demandé; acceptation déduit le centre du token enregistré. Actions révoquer par identifiant sont réservées au super-admin plateforme, donc périmètre volontairement global opérateur (`backend/app/platform/invitations.py:41-141`; `backend/app/platform/router.py:372-455`). |
| Console plateforme | Les listes/agrégations de centres sont globales pour super-admin; cela n'est pas une requête d'un admin locataire (`backend/app/platform/router.py:252-321`). |
| Scripts d'amorçage / opérations admin | Seed center et premier super-admin sont globaux; seed admin choisit centre unique ou ID explicite; désactivation verrouille l'admin et limite le nombre d'admins actifs au centre de cet admin (`backend/scripts/seed_default_center.py:14-28`; `seed_admin.py:35-82`; `deactivate_admin.py:20-63`). |

**Exceptions / limites** : les véhicules ont désormais leur propre `center_id` (FK et index) et unicité taxi/plaque dans le centre depuis la migration 0006 (`backend/app/models.py:193-216`; `backend/alembic/versions/0006_vehicle_tenant_uniqueness.py:34-107`). Les routes admin filtrent par le centre associé à la session. Aucun mécanisme PostgreSQL RLS n'est configuré ou visé à cette phase (`.github/copilot-instructions.md:65-68`). L'application réelle de 0005/0006 est **rapportée par le propriétaire**, mais non introspectée par l'auditeur. `zones` et `driver_status_logs` restent sans usage constaté dans les parcours connus.

## 5. Examen de sécurité face aux règles du projet

| Sujet | Conclusion et preuve |
|---|---|
| Secrets/configuration | `.env` est ignoré, `.env.example` existe; `DATABASE_URL` y est un placeholder masqué dans ce rapport (`.gitignore:8-13`; `.env.example:1-6`). Cependant README backend/racine contient un secret de démonstration local en clair et des valeurs d'exemple d'accès; non reproduites ici (`backend/README.md:1-16,24-38`; `./README.md:94-108`). |
| Environnement | `APP_ENV` accepte development/production, valeur par défaut production et valeurs invalides ramenées à production (`backend/app/config.py:30-37`). Le fichier exemple choisit development, il faut donc ne pas le confondre avec le défaut effectif d'une configuration absente (`.env.example:1`). |
| Mots de passe | Hash Argon2; les cookies et tokens opaque sont stockés par hash SHA-256 (`backend/main.py:43-44,281-318,431-481`; `backend/app/platform/auth.py:14-18`; `backend/app/platform/router.py:154-210`; `backend/app/platform/invitations.py:70-88,90-141`). |
| Comparaison secrets | Sessions utilisent `secrets.compare_digest`; requêtes token identifient par filtre hash SQL (`backend/main.py:222-244`; `backend/app/platform/auth.py:41-48`). |
| Sessions | Cookies HttpOnly, SameSite Strict, TTL 8 h admin / 4 h plateforme, révocation et expiry validées; `Secure` seulement en production (`backend/main.py:281-318`; `backend/app/platform/router.py:154-215`; `backend/app/platform/auth.py:33-65`). Pas de TOTP/MFA ni de récupération de mot de passe repérés; création admin par invitation seulement. |
| Séparation des identités | Cookie, table, dépendance et durée distincts; tests spécifiques interdisent la substitution entre sessions (`backend/app/platform/auth.py:14-65`; `backend/tests/test_platform.py:136-160`). |
| Validation des entrées | `AdminLogin`, gestion chauffeur/véhicule, `Loc`, `LocationBatch`, `Status` et modèles console déclarent `strict=True` et `extra="forbid"`; la validation métier des positions ajoute coordonnées, cap, vitesse, dates, précision, intervalle et vitesse plausible (`backend/main.py:343-448`; `backend/app/locations.py:37-80`; `backend/app/platform/router.py:67-134`; `backend/app/platform/invitations.py:161-169`). |
| Injection SQL | Requêtes applicatives analysées emploient expressions SQLAlchemy (`backend/main.py:224-238,288-290,367-377,417-429,534-577`; `backend/app/platform/router.py:162-166,260-287,348-349,382-384,419-434,465-469`; `backend/app/platform/auth.py:41-61`; `backend/app/platform/invitations.py:48-68,96-115`). Exceptions migrations contiennent du SQL statique constant (`backend/alembic/versions/0002_admin_sessions.py:19`; `0003_platform_console.py:20-28`). Aucune concaténation SQL dynamique repérée (**INFERRED**). |
| CORS / origine | Middleware allowlistée avec credentials et méthodes GET/POST/PATCH; websocket exige une origine connue ou même Host (`backend/main.py:47-55,92-100,259-279`). Ce contrôle ne chiffre pas le transport. |
| HTTP clair | L'URL frontend par défaut est `http://localhost:8000`; les valeurs de développement mobile utilisent aussi HTTP. La confidentialité/intégrité du token chauffeur et des sessions admin dépend du réseau lorsque HTTP est utilisé (`frontend/src/api/client.ts`; `backend/app/config.py:18-24`; `DriverApp/src/api/constants.ts:1-12`; `DriverApp/docs/TECHNICAL_DECISIONS.md:42-43`; `DriverApp/ios/DriverApp/Info.plist:27-35`). L'usage de HTTPS en déploiement n'est pas construit/vérifié. |
| Jeton mobile local | AsyncStorage reçoit et relit le token en clair sur le stockage applicatif (`DriverApp/src/screens/TokenEntryScreen.tsx:19-38`; `DriverApp/src/api/client.ts:32-45`). README décision le confirme (`DriverApp/docs/TECHNICAL_DECISIONS.md:9-16`). |
| Limitation de débit | Aucun limiteur de débit ni configuration associée identifiée dans les routes/dépendances; **ABSENT du code inspecté** (**INFERRED**, `backend/requirements.txt:1-11`; inventaire route ci-dessus). |
| Logging/sensibles | Journal plateforme conserve IP client et User-Agent (200 caractères); échec de login stocke hash SHA-256 d'email (`backend/app/platform/audit.py:10-37`; `backend/app/platform/router.py:173-182`). Aucun numéro complet/tokens connus imprimés dans les logs du chemin normal vérifié; exceptions/audits runtime non exécutés. |
| Rendu frontend / dépendances Leaflet | Les chaînes sont rendues par React ou par des nœuds DOM; aucune occurrence de `innerHTML`, `dangerouslySetInnerHTML` ou `insertAdjacentHTML` n'a été trouvée dans `frontend/src`. Leaflet et son CSS sont importés depuis npm (`frontend/package.json`, `frontend/src/dashboard/MapView.tsx`); aucune référence CDN à Leaflet ne subsiste dans le frontend. La carte charge toutefois les tuiles OpenStreetMap depuis leur service distant. La CSP n'est pas déployée; les en-têtes de sécurité restent différés. |
| Réponses erreurs | Auth admin renvoie erreurs génériques; plateforme et invitation remplacent erreurs de validation par messages génériques (`backend/main.py:313-318`; `backend/app/platform/router.py:43-64`; `backend/app/platform/invitations.py:145-159`). |
| Sauvegarde | Scripts de dump local, somme de contrôle, rétention, tâche planifiable et test restore partiel existent; le propriétaire rapporte restore PASS sur cinq tables. Aucun chiffrement ou stockage distant configuré n'est établi par le code (`scripts/backup/backup-db.ps1:1-208`; `scripts/backup/restore-test.ps1:1-200`; `scripts/backup/register-backup-task.ps1:1-42`). |
| Pip audit | `pip-audit` n'a pas été exécuté pour cette mise à jour; l'état des dépendances Python n'est pas évalué ici (**NON VÉRIFIÉ**). |
| NPM audit frontend | `npm audit` exécuté dans `frontend/` : **0 vulnérabilité** dans l'arbre audité à la date de cette vérification. Ce résultat concerne le lockfile frontend seulement. |

## 6. Tests

- Backend : six modules unitaires suivis, dont `test_admin_auth.py`, `test_devtasks.py`, `test_fake_driver.py`, `test_invitations.py`, `test_locations.py`, `test_platform.py`; ils couvrent aussi validation/déduplication, lots, invitations, gestion admin, et broadcasts par centre (`backend/tests/`). Exécution effectuée pendant cette mise à jour depuis `backend/`, avec `DEV_TASKS_ENABLED` non défini et les tests d'intégration désactivés :
  ```powershell
  & 'C:\td\.venv\Scripts\python.exe' -m pytest -q
  ```
- **Sortie observée** : `165 passed, 1 warning in 15.04s`. Le seul avertissement est une dépréciation Starlette liée à l'utilisation de `httpx` avec `TestClient`. Les tests d'intégration PostgreSQL n'ont pas été activés; aucun accès à une base n'a été effectué.
- Sortie de commande :
  ```text
  ........................................................................ [ 43%]
  ........................................................................ [ 87%]
  .....................                                                    [100%]
  ============================== warnings summary ===============================
  ..\.venv\Lib\site-packages\fastapi\testclient.py:1
    C:\td\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
      from starlette.testclient import TestClient as TestClient  # noqa

  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
  165 passed, 1 warning in 15.04s
  ```
- Les tests unitaires utilisent des doubles pour plusieurs parcours; trois tests d'intégration PostgreSQL sont présents sous `backend/tests_integration/test_vehicle_tenant_isolation.py` et protègent le nom de la base cible `fleet_integration_test` (`backend/tests_integration/conftest.py:19-61,102-136`). Le résultat **3 tests d'intégration réussis est rapporté par le propriétaire** et n'a pas été reproduit par l'auditeur.
- Frontend : `npm test` dans `frontend/` utilise Vitest. Sortie :
  ```text
  > taxi-dispatching-web@1.0.0 test
  > vitest run


   RUN  v5.0.4 C:/td/frontend

   Test Files  7 passed (7)
        Tests  15 passed (15)
     Start at  23:42:37
     Duration  13.31s (environment 86%, import 7%, tests 5%, transform 1%)
  ```
- Frontend : `npm run lint` a terminé avec le code 0 et n'a émis aucune erreur; sortie :
  ```text
  > taxi-dispatching-web@1.0.0 lint
  > eslint .
  ```
- Frontend : `npx tsc --noEmit` s'est terminé avec le code 0 sans sortie.
- Frontend : `npm run build` s'est terminé avec le code 0. Sortie :
  ```text
  > taxi-dispatching-web@1.0.0 build
  > vite build

  vite v8.3.4 building client environment for production...
  transforming...
  ✓ 36 modules transformed.
  rendering chunks...
  computing gzip size...
  dist/index.html                      0.61 kB │ gzip:  0.32 kB
  dist/platform.html                   0.63 kB │ gzip:  0.34 kB
  dist/invite.html                     0.71 kB │ gzip:  0.35 kB
  dist/assets/invite-CozBYODC.css      0.14 kB │ gzip:  0.13 kB
  dist/assets/shared-0vdGLciM.css      3.05 kB │ gzip:  1.17 kB
  dist/assets/platform-CkL3m2Mo.css    6.76 kB │ gzip:  2.13 kB
  dist/assets/main-CfKvadlV.css       24.85 kB │ gzip:  8.74 kB
  dist/assets/invite-DARWe1iS.js       2.27 kB │ gzip:  1.04 kB
  dist/assets/platform-BkYf_Lga.js    14.72 kB │ gzip:  4.02 kB
  dist/assets/main-BNpD7g5D.js       174.79 kB │ gzip: 55.39 kB
  dist/assets/shared-CSs5l-HM.js     223.72 kB │ gzip: 70.29 kB

  ✓ built in 2.42s
  ```
- Frontend : `npm audit` s'est terminé avec le code 0 et la sortie exacte `found 0 vulnerabilities`.
- Aucun test mobile ni vérification manuelle de parité avec l'ancien frontend n'a été exécuté pour cette mise à jour; aucun nombre de tests mobiles n'est rapporté. Le comportement réel sur téléphone et la parité fonctionnelle restent **UNVERIFIED**.

## 7. Exploitation et architecture

Compose ne définit qu'une base Postgres 16 et un volume nommé; il n'y a pas de conteneur backend, frontend ou proxy (`backend/docker-compose.yml:1-15`). `start-backend.ps1` utilise le venv local et démarre Uvicorn lié à loopback (`start-backend.ps1:1-12`). Vite sert le frontend en développement sur `localhost:5173`; la tâche `frontend_serve` lance `npm.cmd run dev` et est Windows uniquement (`frontend/package.json`; `backend/app/platform/devtasks/tasks.py:116-121`). Les trois entrées HTML sont configurées pour le build multipage (`frontend/vite.config.ts`). Variables identifiées : `DATABASE_URL`, `WEB_ORIGINS`, `FRONTEND_BASE_URL`, `DEV_TASKS_ENABLED`, `APP_ENV` et `VITE_API_BASE_URL` (`backend/app/config.py:11-65`; `.env.example:1-6`; `frontend/.env.example`).

Sauvegarde : scripts PowerShell locaux et tâche Windows manuelle présents; pas de stockage hors disque local configuré ni service de supervision des sauvegardes (`scripts/backup/backup-db.ps1:1-208`; `register-backup-task.ps1:1-42`). Le propriétaire rapporte le test restore PASS pour cinq tables; ni ce résultat, ni la tâche sur l'hôte, ni l'existence/protection des fichiers n'ont été vérifiés par l'auditeur. CI/CD, registre, staging, déploiement cloud et monitoring sont **non réalisés** dans le dépôt suivi; ils figurent comme cible/phase suivante dans `./README.md:48-55,167`. L'état d'une machine réelle demeure **UNKNOWN**.

## 8. Défauts connus et éléments restant à traiter

| Gravité | Constat | État / preuve |
|---|---|---|
| Élevée | Pas de HTTPS imposé aux URL utilisées par les clients; token chauffeur en en-tête et session cookies seraient exposés en HTTP non fiable. | VERIFIED pour les valeurs par défaut/code; exploitation réseau non testée (`frontend/src/api/client.ts`; `DriverApp/docs/TECHNICAL_DECISIONS.md:42-43`; cookies `backend/main.py:307-318`). |
| Élevée | Secret de développement local commité comme exemple dans README; valeur volontairement masquée ici. | VERIFIED (`backend/README.md:1-16`; `./README.md:94-108`). |
| Moyenne | Pas de rate limiting identifié sur login, invitations, API ou WebSocket. | INFERRED de l'absence aux routes/dépendances; non testé sous charge. |
| Moyenne | Règles Pydantic déclaratives strictes existent, mais validation métier, limites, intervalles de dates et lots doivent continuer à être exercées; aucun constat actuel d'absence `strict/extra` pour `Loc`, `Status` ou `LocationBatch`. | VERIFIED (`backend/main.py:421-448`; `backend/app/locations.py:37-80`). |
| Moyenne | Token chauffeur persistant via AsyncStorage, sans mécanisme sécurisé natif documenté. | VERIFIED (`DriverApp/src/screens/TokenEntryScreen.tsx:19-38`; décision: `DriverApp/docs/TECHNICAL_DECISIONS.md:9-16`). |
| Moyenne | File et upload batch existent; capacité locale bornée à 1 000 points et rejets serveur peuvent entraîner la perte de points; fonctionnement de l'arrière-plan sur appareil et iOS non vérifié. | VERIFIED dans le code, comportement appareil UNVERIFIED (`DriverApp/src/location/queue.ts:1-90`; `tracker.ts:93-194,220-330`). |
| Moyenne | Durée de conservation/rotation des positions et journaux non configurée; disque local des backups demeure point unique de défaillance. | Scripts observables; rétention concerne fichiers seulement (`scripts/backup/backup-db.ps1:42-116`). |
| Faible | `zones`, `driver_status_logs` et potentiellement des champs véhicule/admin ne sont pas utilisés dans les flux observés. | INFERRED, voir section 2. |
| Faible | Les contraintes véhicule tenant dépendent de la migration 0006; état appliqué non introspecté, application rapportée par le propriétaire. | Modèles et migration vérifiés; application en base rapportée par le propriétaire (`backend/app/models.py:193-216`; `backend/alembic/versions/0006_vehicle_tenant_uniqueness.py:34-107`). |
| Faible | TODO de retrait du lanceur DEV existe; artefacts UI/README de dev task restent dans le repo mais conditionnels. | VERIFIED (`backend/main.py:70-111`; `.env.example:4`). |
| Faible | La CSP n'est pas déployée; les tuiles cartographiques viennent d'OpenStreetMap. | CSP absente de la configuration de déploiement du MVP; aucune référence CDN à Leaflet dans le frontend. |

Les gravités expriment une priorité de suivi pour le contexte d'un MVP local; ce ne sont pas des scores de probabilité calculés.

## 9. Éléments que seul le propriétaire peut vérifier — UNVERIFIED

1. Nombre de lignes, contraintes/index réels, centre par défaut et comptes présents. Le propriétaire rapporte que 0005 et 0006 sont appliquées, mais cet état n'a pas été vérifié directement.
2. Présence et protection des fichiers backup, fonctionnement quotidien, tâche Windows effective, stockage indépendant et capacité/rétention disque. Le propriétaire rapporte un test de restauration PASS sur cinq tables; l'auditeur ne l'a pas reproduit.
3. Démarrage avec les variables et services de sa machine, accès effectif des opérateurs, exposition réseau, HTTPS réel, configuration pare-feu et résultat d'un scénario multi-centre réel.
4. Réception GPS, permissions réelles et continuité lors verrouillage/app en arrière-plan sur chaque version Android/iOS ciblée. Ces comportements restent non vérifiés sur téléphone.
5. Statut de tests end-to-end historiques mentionnés dans README; l'audit ne peut pas les reproduire.
6. Validité, rotation et exposition des secrets locaux ou variables d'environnement en place; aucune valeur `.env` n'a été demandée ou inspectée.
7. Le résultat `npm audit` vaut pour le lockfile frontend consulté le 13 octobre 2026; il ne constitue pas une validation d'autres lockfiles ou d'un artefact mobile.

## 10. Résultats/outils exécutés

- Tree courant : migrations Alembic 0001 à 0006; 0005 déduplique `(driver_id, recorded_at)`, 0006 ajoute `vehicles.center_id` et contraintes uniques par centre. Application 0005/0006 **rapportée par le propriétaire**, non vérifiée par connexion DB.
- Depuis `backend/`, `DEV_TASKS_ENABLED` non défini au lancement : `pytest -q` → `165 passed, 1 warning in 15.04s`; aucun test d'intégration ni accès base.
- Tests d'intégration PostgreSQL : **3 tests réussis, rapporté par le propriétaire**, non reproduits par l'auditeur. Test de restauration : **PASS pour les cinq tables, rapporté par le propriétaire**, non reproduit par l'auditeur.
- Depuis `frontend/`, `npm test` → 7 fichiers et 15 tests passés; `npm run lint` et `npx tsc --noEmit` terminent avec code 0; `npm run build` produit les trois entrées HTML, trois bundles de page et un chunk partagé.
- Depuis `frontend/`, `npm audit` → `found 0 vulnerabilities`.
- `pip-audit` : commande indisponible lors d'un contrôle antérieur; non relancé pour cette mise à jour.
- Comportement réel de l'application sur téléphone : **UNVERIFIED**; aucun test device effectué par l'auditeur.
- Compilation courante du rapport : deux passes `pdflatex -interaction=nonstopmode -halt-on-error`; résultats, pages, références non définies et erreurs consignés après compilation dans `docs/report/README.md`.
- Aucune connexion base, commande psql, lecture `.env`, mise à jour de dépendance ou modification applicative.
