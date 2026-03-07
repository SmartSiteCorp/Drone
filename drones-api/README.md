# DroneControl API

Backend Node.js/TypeScript pour le pilotage de drones en temps reel.
Le projet expose :

- une API REST pour gerer les devices et les liens relay <-> drone,
- une couche Socket.IO pour la telemetrie et les commandes.

## Stack

- Node.js + TypeScript
- Express 5
- Socket.IO 4
- PostgreSQL 16
- Zod (validation)

## Prerequis

- Node.js 18+
- Docker + Docker Compose

## Installation

```bash
cd drones-api
npm install
```

Creer un fichier `.env` a la racine :

```env
PORT=7281
DATABASE_URL=postgresql://drones:drones_password@localhost:5432/drones_api
MASTER_KEY=change-me
```

## Demarrage rapide

1. Lancer PostgreSQL

```bash
docker-compose up -d
```

2. Lancer l'API

```bash
npm run dev
```

API disponible sur `http://localhost:7281`.

## Structure principale

```text
src/
  app.ts
  main.ts
  db/pool.ts
  http/router.ts
  modules/
    auth/
    devices/
    relay-links/
  realtime/
    authApiKey.ts
    rooms.ts
    handlers/
```

## API REST

### Base

- `GET /` : message de bienvenue
- `GET /health` : statut API (`{ ok: true }`)

### Devices

- `POST /api/devices`
- `GET /api/devices?limit=100&offset=0`
- `GET /api/devices/relay`
- `GET /api/devices/dashboard`
- `GET /api/devices/:id`

Exemple creation :

```http
POST /api/devices
Content-Type: application/json

{
  "name": "Relay-01",
  "type": "relay"
}
```

Types utilises dans le code applicatif :

- `relay`
- `drone`
- `dashboard`
- `admin`

La cle API est retournee une seule fois dans la reponse de creation.

### Liens relay <-> drone

- `POST /api/relay-links`

Payload :

```json
{
  "relayDeviceId": "uuid",
  "droneDeviceId": "uuid"
}
```

## WebSocket (Socket.IO)

Connexion avec API key via `auth.apiKey` :

```js
import { io } from "socket.io-client";

const socket = io("http://localhost:7281", {
  auth: { apiKey: "votre_api_key" },
});

socket.on("connected", (data) => {
  console.log(data);
});
```

### Telemetrie

- `telemetry:push` (client -> serveur)
- `telemetry:push:ack` (serveur -> client)
- `telemetry:subscribe` / `telemetry:subscribed`
- `telemetry:unsubscribe` / `telemetry:unsubscribed`
- `telemetry:update`
- `app:error`

Payload minimal `telemetry:push` :

```ts
{
  droneId: string;
  ts: number;
}
```

### Commandes

Evenement d'envoi : `commande:send`

Payload accepte :

```ts
"RTL"
```

ou

```ts
{
  label: "Démarrer" | "Mission Auto" | "Loiter" | "RTL" | "Land" | "Stop";
  deviceID: string;
}
```

Retour :

- ACK callback (`{ ok: true|false, ... }`)
- `commande:status`
- `relay:command` (diffuse vers la room du relay cible)

## Scopes

- `telemetry:write`
- `telemetry:read`
- `commands:write`
- `commands:read`
- `devices:manage`
- `keys:manage`

## Point d'attention schema SQL

Le code autorise les types `dashboard` et `admin`, mais `database/init.sql` contient encore une contrainte `devices_type_chk` avec `relay`, `drone`, `client`, `server`.

Si vous creez un `dashboard` ou un `admin`, adaptez la contrainte SQL pour aligner la base sur le code.

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