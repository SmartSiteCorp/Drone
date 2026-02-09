import { Router } from "express";
import { createDeviceHandler } from "./devices.controller";

export const devicesRoutes = Router();

// MVP: pas protégé au début (on mettra une master key / admin scope juste après)
devicesRoutes.post("/", (req, res, next) => {
  createDeviceHandler(req, res).catch(next);
});
