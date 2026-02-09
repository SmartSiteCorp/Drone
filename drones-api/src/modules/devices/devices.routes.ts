import { Router } from "express";
import { createDeviceHandler, getDeviceByIdHandler, listDevicesHandler } from "./devices.controller";

export const devicesRoutes = Router();

// MVP: pas protégé au début (on mettra une master key / admin scope juste après)
devicesRoutes.post("/", (req, res, next) => {
  createDeviceHandler(req, res).catch(next);
});

devicesRoutes.get("/", (req, res, next) => {
  listDevicesHandler(req, res).catch(next);
});

devicesRoutes.get("/:id", (req, res, next) => {
  getDeviceByIdHandler(req, res).catch(next);
});

