import { Router } from "express";
import {
  createDeviceHandler,
  getDeviceByIdHandler,
  listDevicesHandler,
  getAllRelays,
  // getAllDashboards,
  getAllDrones,
  deleteDeviceHandler,
} from "./devices.controller";

export const devicesRoutes = Router();

// MVP: pas protégé au début (on mettra une master key / admin scope juste après)
devicesRoutes.post("/", (req, res, next) => {
  createDeviceHandler(req, res).catch(next);
});
// obtenir tous les devices (avec pagination optionnelle via query params limit & offset)
devicesRoutes.get("/", (req, res, next) => {
  listDevicesHandler(req, res).catch(next);
});

//  obtenir tous les relays
devicesRoutes.get("/relay", (req, res, next) => {
  getAllRelays(req, res).catch(next);
});

devicesRoutes.get("/drone", (req, res, next) => {
  getAllDrones(req, res).catch(next);
});

// // obtenir tous les dashboards
// devicesRoutes.get("/dashboard", (req, res, next) => {
//   getAllDashboards(req, res).catch(next);
// });

devicesRoutes.get("/:id", (req, res, next) => {
  getDeviceByIdHandler(req, res).catch(next);
});

devicesRoutes.delete("/:id", (req, res, next) => {
  deleteDeviceHandler(req, res).catch(next);
});
