
#  MAVLink → DroneControl Relay

Ce projet est un **relay de télémétrie drone** qui lit un flux **MAVLink** (ArduPilot / PX4) et transmet en temps réel les données vers un backend **DroneControl** via **Socket.IO**.

Il permet notamment de remonter :

* 📍 GPS (fix, satellites, position)
* 🔋 Batterie (voltage, courant, % restant)
* 🧭 EKF Status (variances, flags)
* 🚁 Arm / Disarm
* 🎮 Changements de mode de vol
* ⚠️ Warnings critiques via `STATUSTEXT` (failsafe, GPS, EKF…)

---

## ✨ Fonctionnement

Le relay est basé sur une architecture en **2 threads** :

| Thread             | Rôle                                                                   |
| ------------------ | ---------------------------------------------------------------------- |
| Producer MAVLink   | Lit en continu le flux MAVLink et pousse des événements dans une queue |
| Consumer Socket.IO | Consomme la queue et envoie les événements au backend DroneControl     |

Cela garantit :

* pas de blocage MAVLink
* anti-spam via limitation de fréquence
* transmission fiable même avec reconnect Socket.IO

---

## 📦 Installation

### 1. Cloner le projet

```bash
git clone https://github.com/Drone-conception/relay-mavlink
cd mavlink-relay
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

Librairies utilisées :

* `pymavlink`
* `python-socketio`
* `python-dotenv`

---

## ⚙️ Configuration

Créer un fichier `.env` à la racine :

```env
DRONECONTROL_URL=http://localhost:7281
DRONECONTROL_API_KEY=dc_xxxxxxxxxxxxxxxxxxxxx
DRONE_ID=157a9912c-e905-449a-a077-5b9666f36cf1

MAVLINK_ENDPOINT=udp:0.0.0.0:14550

GPS_MIN_INTERVAL_S=0.2
BATT_MIN_INTERVAL_S=1.0
```

---

### 🔑 Variables importantes

| Variable               | Description                     |
| ---------------------- | ------------------------------- |
| `DRONECONTROL_URL`     | Adresse du serveur DroneControl |
| `DRONECONTROL_API_KEY` | Clé API pour `telemetry:write`  |
| `DRONE_ID`             | Identifiant unique du drone     |
| `MAVLINK_ENDPOINT`     | Source MAVLink (UDP, serial…)   |
| `GPS_MIN_INTERVAL_S`   | Intervalle min GPS (anti-spam)  |
| `BATT_MIN_INTERVAL_S`  | Intervalle min batterie         |

---

## ▶️ Lancement

Démarrer simplement :

```bash
python relay.py
```

Sortie attendue :

```
[config] MAVLINK_ENDPOINT=udp:0.0.0.0:14550
[mav] heartbeat ok
[sio] connected
[mav] producer started
[sio] consumer started
```

---

## 📡 Événements envoyés

Tous les messages sont envoyés au backend via :

```js
socket.emit("telemetry:push", payload)
```

Avec un champ `type` permettant de distinguer :

| Type      | Contenu                                  |
| --------- | ---------------------------------------- |
| `gps`     | Fix GPS, lat/lon/alt, satellites         |
| `battery` | Voltage, courant, % restant              |
| `ekf`     | EKF flags + variances                    |
| `mode`    | Changements de mode de vol               |
| `arm`     | Arm / Disarm                             |
| `warning` | STATUSTEXT filtrés (failsafe, GPS, EKF…) |

---

### Exemple payload GPS

```json
{
  "droneId": "drone-01",
  "type": "gps",
  "fixLabel": "FIX_3D",
  "lat": 48.8566,
  "lon": 2.3522,
  "satellites": 12
}
```

---

### Exemple warning failsafe

```json
{
  "type": "warning",
  "category": "BATTERY",
  "severityLabel": "CRITICAL",
  "text": "Failsafe: Battery low"
}
```

---

## 🛡️ Sécurité & Robustesse

* Queue limitée à `2000` événements (drop si overflow)
* Anti-spam GPS/Battery configurable
* Reconnexion automatique Socket.IO
* Aucun crash si backend déconnecté

---

## 🚀 Améliorations possibles

* Support multi-drones
* Historique local en cas de perte réseau
* Ajout altitude relative + vitesse
* Ajout d’un event dédié `telemetry:warning`

---

## 👨‍💻 Auteur

Projet développé par **Aurélien**
Relay MAVLink → DroneControl backend
