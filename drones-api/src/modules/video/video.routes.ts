import { Router } from "express";
import {
  createCameraStreamTokenHandler,
  mediaMTXAuthHandler,
  requestCameraStreamHandler,
  requireVideoScope,
} from "./video.controller";

export const videoRoutes = Router();

videoRoutes.post("/mediamtx-auth", (req, res, next) => {
  mediaMTXAuthHandler(req, res).catch(next);
});

videoRoutes.post(
  "/:droneId/access-token",
  requireVideoScope("telemetry:read", "dashboard"),
  (req, res, next) => {
    createCameraStreamTokenHandler(req, res).catch(next);
  },
);

videoRoutes.post(
  "/:droneId/start",
  requireVideoScope("telemetry:read", "dashboard"),
  (req, res, next) => {
    requestCameraStreamHandler(req, res, "start").catch(next);
  },
);

videoRoutes.post(
  "/:droneId/stop",
  requireVideoScope("telemetry:read", "dashboard"),
  (req, res, next) => {
    requestCameraStreamHandler(req, res, "stop").catch(next);
  },
);

