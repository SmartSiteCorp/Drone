import { Router } from "express";
import { devicesRoutes } from "../modules/devices/devices.routes";

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

// Routes métier
router.use("/api/devices", devicesRoutes);
