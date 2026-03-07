# Test Relay - Verification autorisation Drone <-> Relay

Ce test valide :

- l'authentification Socket.IO via API key,
- l'envoi de `telemetry:push`,
- l'autorisation relay -> drone,
- le rejet des drones non autorises.

## Fichier concerne

- `test/test-relais.js`

## Prerequis

Depuis `drones-api` :

```bash
npm install
```

Si `socket.io-client` n'est pas installe, ajouter :

```bash
npm install socket.io-client
```

## Preparation

1. Creer un device de type `relay` et recuperer son API key.
2. Creer un device de type `drone`.
3. Creer le lien actif :

```http
POST /api/relay-links
Content-Type: application/json

{
  "relayDeviceId": "<uuid-relay>",
  "droneDeviceId": "<uuid-drone-autorise>"
}
```

4. Dans `test/test-relais.js`, remplacer :

- `API_KEY` par la cle du relay,
- le `droneId` du test vert par le drone autorise,
- le `droneId` du test rouge par un UUID non autorise.

## Lancement

```bash
node ./test/test-relais.js
```

## Resultats attendus

Drone autorise :

```text
ACK: { ok: true, droneId: "...", ts: ... }
```

Drone non autorise :

```text
ERROR: {
  event: 'telemetry:push',
  message: 'Drone non autorisé pour ce relay',
  droneId: '...'
}
```

## Evenement de connexion utile

Au `connected`, le serveur renvoie notamment :

```json
{
  "ok": true,
  "deviceId": "...",
  "deviceType": "relay",
  "scopes": ["telemetry:write", "commands:read"],
  "allowedDroneIds": ["..."]
}
```

Le `droneId` envoye dans le test autorise doit etre present dans `allowedDroneIds`.

## Note securite

Le fichier `test/test-relais.js` contient actuellement une API key en dur. Ne pas committer de vraie cle en production.

## Warning Node possible

Si un warning `MODULE_TYPELESS_PACKAGE_JSON` apparait, vous pouvez :

- le laisser (le script peut quand meme fonctionner),
- ajouter `"type": "module"` dans `package.json`,
- ou convertir le script en CommonJS (`require`).