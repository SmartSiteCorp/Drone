# 🧪 Test Relay – Vérification de l’autorisation Drone ↔ Relay

Ce script permet de tester :

* 🔐 L’authentification via API key
* 📡 L’envoi de télémétrie (`telemetry:push`)
* 🔗 La vérification d’association relay → drone
* 🚫 Le blocage des drones non autorisés

---

## 📁 Fichier

Créer un fichier :

```
test/test-relais.js
```

---

## 📦 Prérequis

Installer le client Socket.IO :

```bash
npm install socket.io-client
```

---

## 🧠 Script de test

```js
import { io } from "socket.io-client";

const API_KEY = "COLLE_ICI_LA_VRAIE_API_KEY_DU_RELAY";

const socket = io("http://localhost:7281", {
  auth: {
    apiKey: API_KEY,
  },
});

socket.on("connect", () => {
  console.log("Connected as relay");

  // 🟢 TEST 1 — drone autorisé
  socket.emit("telemetry:push", {
    droneId: "UUID_DRONE_AUTORISÉ",
    ts: Date.now(),
    lat: 48.85,
    lon: 2.35,
    alt: 120,
  });

  // 🔴 TEST 2 — drone non autorisé
  setTimeout(() => {
    socket.emit("telemetry:push", {
      droneId: "UUID_FAUX_DRONE",
      ts: Date.now(),
      lat: 0,
      lon: 0,
      alt: 0,
    });
  }, 2000);
});

socket.on("telemetry:push:ack", (data) => {
  console.log("ACK:", data);
});

socket.on("app:error", (err) => {
  console.log("ERROR:", err);
});

socket.on("connected", (data) => {
  console.log("Server connected event:", data);
});
```

---

## ▶️ Lancer le test

Depuis le dossier `drones-api` :

```bash
node ./test/test-relais.js
```

---

## 🎯 Résultats attendus

### ✅ Drone autorisé

```
ACK: { ok: true, droneId: "...", ts: ... }
```

### ❌ Drone non autorisé

```
ERROR: {
  event: 'telemetry:push',
  message: 'Drone non autorisé pour ce relay'
}
```

---

## 🔍 Vérification côté serveur

Au moment de la connexion, le serveur renvoie :

```json
{
  "ok": true,
  "deviceId": "...",
  "deviceType": "relay",
  "scopes": ["telemetry:write", "commands:read"],
  "allowedDroneIds": ["..."]
}
```

Le `droneId` utilisé dans le test doit être présent dans `allowedDroneIds`.

---

## ⚠️ Warning Node (facultatif)

Si Node affiche :

```
MODULE_TYPELESS_PACKAGE_JSON warning
```

Deux options :

### Option 1 — Ignorer (aucun impact)

### Option 2 — Ajouter dans package.json :

```json
{
  "type": "module"
}
```

### Option 3 — Passer en CommonJS

Remplacer :

```js
import { io } from "socket.io-client";
```

par :

```js
const { io } = require("socket.io-client");
```

---

## 🛡 Ce que ce test valide

Ce script confirme que ton backend applique correctement :

* API key authentication
* Scope checking
* Association relay ↔ drone en base
* Contrôle d’autorisation en temps réel
* Isolation par rooms Socket.IO