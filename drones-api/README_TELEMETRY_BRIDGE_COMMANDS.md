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
- `POST /api/video/:droneId/start`
- `POST /api/video/:droneId/stop`
- `POST /api/video/:droneId/access-token`
- `POST /api/video/mediamtx-auth` (callback interne MediaMTX)

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

### Test API avec deux drones

Avec l'API et PostgreSQL demarres, le test cree automatiquement deux couples relais-drone distincts et un dashboard, puis les supprime a la fin. Lancer :

```powershell
npm run test:multi-drones
```

Le test verifie que chaque relay ne peut publier que pour son drone, que chaque dashboard ne recoit que la telemetrie de son drone et que les commandes `Stop` arrivent uniquement au relay associe. Il ne verifie pas la livraison MAVLink ni le vol reel. Voir `test/README_MULTI_DRONES.md` pour les details.

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
- `docker-compose.yml` expose `55432:5432` (port hôte 55432, port conteneur 5432).
- Pour l'API lancée sur la machine hôte, `DATABASE_URL` doit donc viser `localhost:55432`.
- Démarrer le service avec `docker compose up -d db` avant de lancer l'API.

## 9) Fichiers de reference

- `src/http/router.ts`
- `src/realtime/index.ts`
- `src/realtime/handlers/telemetry.ts`
- `src/realtime/handlers/commands.ts`
- `src/realtime/handlers/connection.ts`
- `test/relay-airsim-bridge.py`
- `src/modules/relay-links/*`
- `src/modules/devices/*`

## 10) Flux caméra AirSim avec MediaMTX

MediaMTX reçoit le flux RTSP H.264 publié par `relay-mavlink/relay.py`, puis le
sert au navigateur en WebRTC (faible latence) ou HLS. Le relay capture la caméra
AirSim `down` via RPC uniquement après réception de `relay:video:start`. L'API
ne transporte plus les images : elle contrôle le relay et valide l'authentification
MediaMTX.

Configurer le `.env` du relay :

```env
DRONECONTROL_URL=http://localhost:7281
DRONECONTROL_API_KEY=<clé API du relay associé au drone>
DRONE_ID=<identifiant du drone>
MEDIAMTX_RTSP_URL=rtsp://127.0.0.1:8554
CAMERA_NAME=down
CAMERA_VEHICLE_NAME=Copter
CAMERA_STREAM_HZ=10
```

Installer les dépendances du relay avec `pip install -r relay-mavlink/requirements.txt`.
Démarrer PostgreSQL, l'API et MediaMTX avec `docker compose up -d db mediamtx`
(depuis `drones-api`), puis lancer `python relay.py` depuis `relay-mavlink`.
AirSim doit être actif et son RPC accessible depuis le relay.

Pour tester les routes depuis PowerShell, avec le serveur API et le relay actifs :

```powershell
$env:API_URL="http://localhost:7281"
$env:DASHBOARD_API_KEY="<clé dashboard avec telemetry:read>"
$env:DRONE_ID="<identifiant du drone>"
node test/test-camera-stream.js start
node test/test-camera-stream.js stop
```

La commande `start` affiche la page WebRTC de MediaMTX et le mot de passe temporaire à saisir dans
la demande d'authentification du navigateur. L'URL HLS de secours est également
affichée. Après avoir testé, lancer `node test/test-camera-stream.js stop`.

Le dashboard déclenche l'envoi et demande un jeton avec sa clé et le scope
`telemetry:read` :

```js
await fetch(`${API_URL}/api/video/${droneId}/start`, {
  method: "POST",
  headers: { "x-api-key": dashboardApiKey },
});
```

```js
const response = await fetch(`${API_URL}/api/video/${droneId}/access-token`, {
  method: "POST",
  headers: { "x-api-key": dashboardApiKey },
});
const { whepUrl, token } = await response.json();
const reader = new MediaMTXWebRTCReader({
  url: whepUrl,
  token,
  onTrack: (event) => {
    document.querySelector("#drone-camera").srcObject = event.streams[0];
  },
  onError: console.error,
});
```

```html
<video id="drone-camera" autoplay muted playsinline controls></video>
```

Pour arrêter l'envoi, appeler `POST /api/video/${droneId}/stop` avec le même
header `x-api-key`.

Le jeton expire après cinq minutes et ne donne accès qu'au flux du drone demandé.
MediaMTX appelle l'API d'authentification pour chaque publication et lecture.
En production, configure `webrtcAdditionalHosts` dans `mediamtx.yml` avec le nom
DNS/IP public du serveur; `localhost` ne convient qu'au test sur le même poste.

---

Si vous voulez une API 100% HTTP pour commandes + flight-info, il faut (re)brancher des modules telemetry/commands REST dans `src/http/router.ts`.
