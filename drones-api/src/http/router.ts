import { Router } from "express";
import { devicesRoutes } from "../modules/devices/devices.routes";
import { relayLinksRoutes } from "../modules/relay-links/relay-links.routes";

export const router = Router();

router.get("/", (_req, res) => {
  res.json({
    message: "Bienvenue sur l’API DroneControl",
    status: "ok",
  });
});

router.get("/health", (_req, res) => {
  res.json({ ok: true });
});

// Routes métier du domaine "devices" (gestion des drones, relays, dashboards)
router.use("/api/devices", devicesRoutes);
// Routes métier du domaine "relay-links" (gestion des liens entre relays et drones)
router.use("/api/relay-links", relayLinksRoutes);