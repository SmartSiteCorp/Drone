# DroneControl - Telemetry Bridge and Commands Guide

Ce document explique les changements recents autour de:
- la telemetrie temps reel,
- le bridge MAVLink <-> Socket.IO,
- l envoi de commandes drone.

Il est base sur l etat actuel du code dans src/ et test/.

## 1) Vue d ensemble

Architecture logique:
1. SITL/AirSim emet du MAVLink en UDP.
2. Le bridge Python lit MAVLink et pousse la telemetrie vers l API via Socket.IO (`telemetry:push`).
3. L API diffuse la telemetrie aux dashboards abonnes (`telemetry:update`).
4. Le dashboard envoie les commandes via Socket.IO (`commande:send`).
5. L API relaye la commande vers le bon relay (`relay:command`).
6. Le bridge recoit la commande et l envoie au drone en MAVLink.

## 2) Ce qui a change (resume)

### 2.1 Telemetry
- Validation du payload telemetrie cote API (`droneId`, `ts`).
- Controle d autorisation relay -> drone via `allowedDroneIds`.
- Diffusion dashboard via room drone.

### 2.2 Commands Socket.IO
- Handler `commande:send` avec:
  - rate limit par socket,
  - verification du scope `commands:write`,
  - validation du payload,
  - recherche du relay actif pour le drone,
  - emission `relay:command` vers la room relay.
- Nettoyage du listener a la deconnexion.

### 2.3 Bridge Python
- Support de plusieurs modes de routage drone:
  - `DRONE_ID` (single drone),
  - `DRONE_ID_BY_SYSID` (mapping statique),
  - `AUTO_CONFIG_FROM_API=1` (mapping dynamique depuis API, si endpoint disponible).
- Emission telemetrie partielle (pas besoin d attendre GPS complet).
- Mapping de commandes MAVLink ajoute:
  - ARM,
  - ARM_FORCE,
  - DISARM,
  - GUIDED,
  - STABILIZE,
  - AUTO / Mission Auto,
  - Loiter,
  - RTL,
  - Land.
- Log d ACK MAVLink pour ARM/DISARM.

## 3) Endpoints HTTP disponibles (etat actuel src/http/router.ts)

Routes REST exposees actuellement:
- `GET /`
- `GET /health`
- `POST /api/devices`
- `GET /api/devices`
- `GET /api/devices/:id`
- `GET /api/devices/relay`
- `GET /api/devices/drone`
- `DELETE /api/devices/:id`
- `POST /api/relay-links`
- `GET /api/relay-links`
- `GET /api/relay-links/by-relay`
- `GET /api/relay-links/by-drone`
- `DELETE /api/relay-links/:id`

Important:
- Le routage HTTP des commandes n est pas branche dans le router actuel.
- Le chemin `GET /api/flight-info/:droneId` n est pas branche dans le router actuel.
- Les commandes passent donc par Socket.IO (`commande:send`) dans cet etat.

## 4) Socket.IO - evenements a utiliser

### 4.1 Connexion
Connexion avec API key:
- `auth.apiKey`, ou
- header `x-api-key` (fallback utile en test).

### 4.2 Telemetrie
- Relay -> API: `telemetry:push`
- API -> Relay: `telemetry:push:ack`
- Dashboard -> API: `telemetry:subscribe`, `telemetry:unsubscribe`
- API -> Dashboard: `telemetry:update`, `telemetry:subscribed`, `telemetry:unsubscribed`
- Erreurs: `app:error`

Payload minimum `telemetry:push`:
{
  "droneId": "uuid",
  "ts": 1750000000000
}

### 4.3 Commandes
Event d envoi: `commande:send`

Labels acceptes cote API (handler Socket actuel):
- ARM
- DISARM
- Mission Auto
- Loiter
- RTL
- Land
- Stop
- MOTOR_TEST

Exemple:
{
  "label": "ARM",
  "droneId": "uuid"
}

Cas MOTOR_TEST:
{
  "label": "MOTOR_TEST",
  "droneId": "uuid",
  "percent": 15,
  "durationSeconds": 2,
  "motor": "ALL"
}

## 5) Bridge - variables d environnement

Variables principales:
- `API_URL` (defaut: http://localhost:7281)
- `RELAY_API_KEY` (obligatoire)
- `MAVLINK_ENDPOINT` (defaut: udpin:0.0.0.0:14550)
- `PUSH_HZ` (defaut: 2)

Routage drone:
- `DRONE_ID` (single drone)
- `DRONE_ID_BY_SYSID` (JSON, exemple: {"1":"uuid-drone-1","2":"uuid-drone-2"})
- `AUTO_CONFIG_FROM_API` (1/0)
- `CONFIG_REFRESH_SEC` (defaut: 5)

## 6) Modes d exploitation recommandes

### Mode A - Simple (single drone)
Quand commencer vite:
- `DRONE_ID=<uuid-drone>`
- `AUTO_CONFIG_FROM_API=0`

### Mode B - Multi-drone statique
- `DRONE_ID_BY_SYSID={...}`
- `AUTO_CONFIG_FROM_API=0`

### Mode C - Multi-drone dynamique (si API de config disponible)
- `AUTO_CONFIG_FROM_API=1`
- Le bridge lit periodiquement le mapping sysid->drone via API.

## 7) Checklist run complet

1. Demarrer DB: `docker compose up -d`
2. Demarrer API: `npm run dev`
3. Creer relay + drone + lien relay-drone.
4. Lancer le bridge Python.
5. Lancer SITL/AirSim avec sortie UDP vers le port ecoute par le bridge.
6. Verifier logs bridge:
   - Connected to API
   - Waiting MAVLink heartbeat...
   - MAVLink heartbeat received
   - telemetry:push ...

## 8) Troubleshooting

### 8.1 `ConnectionError: namespace /`
- Verifier `RELAY_API_KEY`.
- Regenerer une cle relay si doute.
- Verifier que l API tourne bien sur `API_URL`.

### 8.2 Pas de `MAVLink heartbeat received`
- Le bridge ne recoit pas l UDP MAVLink.
- Verifier IP/port de sortie SITL et `MAVLINK_ENDPOINT`.
- En WSL, preferer un `--out udp:127.0.0.1:14550` si bridge tourne aussi en WSL.

### 8.3 Telemetrie visible en Socket mais pas en HTTP
- Dans l etat actuel du router source, `flight-info` n est pas expose.
- Soit consommer la telemetrie en Socket.IO,
- soit rebrancher des routes telemetry HTTP dans `src/http/router.ts`.

### 8.4 Port PostgreSQL
- `docker-compose.yml` expose actuellement `5432:5432`.
- `.env` peut pointer vers `55432` selon les editions locales.
- Aligner `DATABASE_URL` avec le port effectivement expose.

## 9) Fichiers de reference

- `src/http/router.ts`
- `src/realtime/index.ts`
- `src/realtime/handlers/telemetry.ts`
- `src/realtime/handlers/commands.ts`
- `src/realtime/handlers/connection.ts`
- `test/relay-airsim-bridge.py`
- `src/modules/relay-links/*`
- `src/modules/devices/*`

---

Si vous voulez une API 100% HTTP pour commandes + flight-info, il faut (re)brancher des modules telemetry/commands REST dans `src/http/router.ts`.
