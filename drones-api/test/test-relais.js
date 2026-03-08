import { io } from "socket.io-client";

const API_KEY = "dc_lHdWt5yS-ORJF6Ji55--rJvK3l8xD7jb.Pi2b-q5gjfhxUk1vcrggiZqxAhPBTvTP";

const socket = io("http://localhost:7281", {
  auth: {
    apiKey: API_KEY,
  },
});

socket.on("connect", () => {
  console.log("Connected as relay");

  // 🟢 TEST 1 — drone autorisé
  socket.emit("telemetry:push", {
    droneId: "84086f60-491a-4d2d-a566-3727fc86a1f0",
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

// 🎮 Écoute des commandes du serveur
socket.on("relay:command", (data) => {
  console.log("🎮 Commande reçue du serveur:", data);
  
  const { commandId, label, droneId, requestedBy } = data;
  
  // Simulation d'exécution de la commande sur le drone
  console.log(`🚁 Exécution de "${label}" sur le drone ${droneId}...`);
  
  setTimeout(() => {
    console.log(`✅ Commande ${label} exécutée pour drone ${droneId}`);
    
    // Envoyer un ACK au serveur (optionnel)
    socket.emit("relay:command:ack", {
      commandId,
      droneId,
      status: "executed",
      ts: Date.now(),
    });
  }, 500);
});