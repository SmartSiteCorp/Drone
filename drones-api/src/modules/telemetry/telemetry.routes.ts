import { Router } from "express";
import {
  getDroneTelemetryConfigHandler,
  getLatestTelemetryHandler,
  listRelayTelemetryConfigHandler,
  upsertDroneTelemetryConfigHandler,
} from "./telemetry.controller";

export const telemetryRoutes = Router();

telemetryRoutes.get("/config/by-relay", (req, res, next) => {
  listRelayTelemetryConfigHandler(req, res).catch(next);
});

telemetryRoutes.put("/config/:droneId", (req, res, next) => {
  upsertDroneTelemetryConfigHandler(req, res).catch(next);
});

telemetryRoutes.get("/config/:droneId", (req, res, next) => {
  getDroneTelemetryConfigHandler(req, res).catch(next);
});

telemetryRoutes.get("/:droneId", (req, res, next) => {
  getLatestTelemetryHandler(req, res).catch(next);
});
