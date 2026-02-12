# DroneControl API

API backend pour la gestion et le contrôle de drones en temps réel.  
Elle fournit une **API REST** pour la gestion des appareils et une **connexion WebSocket (Socket.IO)** pour la télémétrie et les commandes temps réel.

---

## Stack technique

- **Runtime** : Node.js + TypeScript
- **Framework HTTP** : Express 5
- **WebSocket** : Socket.IO 4
- **Base de données** : PostgreSQL 16
- **Validation** : Zod
- **Sécurité** : Helmet, CORS, authentification par API Key

---

## Prérequis

- Node.js 18+
- Docker & Docker Compose (pour PostgreSQL)

---

## Installation

```bash
# Cloner le repo
cd drones-api

# Installer les dépendances
npm install

# Copier et configurer les variables d'environnement
cp .env.example .env
````

---

## Configuration

Créer un fichier `.env` à la racine :

```env
PORT=7281
DATABASE_URL="postgresql://drones:drones_password@localhost:5432/drones_api"
MASTER_KEY="your-secure-master-key"
```

| Variable       | Description                      | Défaut |
| -------------- | -------------------------------- | ------ |
| `PORT`         | Port du serveur HTTP             | `7281` |
| `DATABASE_URL` | URL de connexion PostgreSQL      | —      |
| `MASTER_KEY`   | Clé maître pour l’administration | —      |

---

## Démarrage

### 1. Lancer la base de données

```bash
docker-compose up -d
```

### 2. Initialiser le schéma

```bash
docker exec -i drones-api-db psql -U drones -d drones_api < sql/init.sql
```

### 3. Lancer le serveur

```bash
# Mode développement (hot reload)
npm run dev

# Mode production
npm run build
npm start
```

Serveur accessible sur :

```
http://localhost:7281
```

---

## Architecture

```
src/
├── app.ts              # Configuration Express
├── main.ts             # Point d’entrée
├── db/
│   └── pool.ts         # Pool PostgreSQL
├── http/
│   ├── router.ts
│   └── middlewares/
│       └── errorHandler.ts
├── modules/
│   ├── auth/
│   │   ├── apiKeys.crypto.ts
│   │   └── scopes.ts
│   └── devices/
│       ├── devices.controller.ts
│       ├── devices.mapper.ts
│       ├── devices.model.ts
│       ├── devices.routes.ts
│       ├── devices.schemas.ts
│       └── devices.service.ts
└── realtime/
    ├── authApiKey.ts
    ├── index.ts
    ├── io.ts
    ├── rooms.ts
    ├── scopes.ts
    └── handlers/
        ├── commands.ts
        ├── connection.ts
        └── telemetry.ts
```

---

## API REST

### Health check

```http
GET /health
```

Réponse :

```json
{ "ok": true }
```

---

### Devices

#### Créer un appareil

```http
POST /api/devices
Content-Type: application/json

{
  "name": "Relay-01",
  "type": "relay",
  "scopes": ["telemetry:write", "commands:read"]
}
```

Types disponibles :

* `relay`
* `dashboard`
* `admin`

⚠️ La valeur de l’API Key est retournée **une seule fois**.

---

#### Lister les appareils

```http
GET /api/devices?limit=100&offset=0
```

#### Récupérer un appareil

```http
GET /api/devices/:id
```

---

## WebSocket (Socket.IO)

### Connexion

```js
import { io } from "socket.io-client";

const socket = io("http://localhost:7281", {
  auth: {
    apiKey: "votre-api-key"
  }
});

socket.on("connected", (data) => {
  console.log("Connecté :", data);
});

socket.on("app:error", (err) => {
  console.error("Erreur :", err);
});
```

---

## Télémétrie

### Événements

| Événement             | Direction        | Description           |
| --------------------- | ---------------- | --------------------- |
| `telemetry:push`      | Client → Serveur | Envoi de télémétrie   |
| `telemetry:push:ack`  | Serveur → Client | Accusé de réception   |
| `telemetry:subscribe` | Client → Serveur | Abonnement à un drone |
| `telemetry:update`    | Serveur → Client | Diffusion temps réel  |

### Payload `telemetry:push`

```ts
{
  droneId: string;
  ts: number;
  lat?: number;
  lon?: number;
  alt?: number;
  groundspeed?: number;
  mode?: string;
}
```

---

## Commandes

### Payload `command:send`

```ts
{
  relayId: string;
  droneId?: string;
  command: "RTL" | "LOITER" | "TAKEOFF" | "LAND";
  params?: Record<string, unknown>;
}
```

---

## Scopes & permissions

| Scope             | Description            |
| ----------------- | ---------------------- |
| `telemetry:write` | Envoyer la télémétrie  |
| `telemetry:read`  | Lire la télémétrie     |
| `commands:write`  | Envoyer des commandes  |
| `commands:read`   | Recevoir des commandes |
| `devices:manage`  | Gérer les devices      |
| `keys:manage`     | Gérer les clés API     |

### Scopes par défaut

| Type      | Scopes                             |
| --------- | ---------------------------------- |
| relay     | `telemetry:write`, `commands:read` |
| dashboard | `telemetry:read`, `commands:write` |
| admin     | `devices:manage`, `keys:manage`    |

---

## Base de données

### Tables principales

#### `devices`

* `id` (UUID)
* `name`
* `type`
* `created_at`

#### `api_keys`

* `device_id`
* `key_prefix`
* `key_hash`
* `scopes`
* `revoked_at`
* `expires_at`
* `last_used_at`

---

## Scripts npm

| Commande        | Description                   |
| --------------- | ----------------------------- |
| `npm run dev`   | Développement avec hot reload |
| `npm run build` | Build TypeScript              |
| `npm start`     | Lancement production          |

---

## Statut du projet

🚧 Projet en cours de développement
Objectif : **backend temps réel robuste pour drones autonomes et systèmes embarqués**

# Auteur
Projet développé par Aurélien
Architecture orientée drones autonomes & systèmes temps réel