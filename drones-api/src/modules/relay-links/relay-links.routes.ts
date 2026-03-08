import { Router } from "express";
import {
  createRelayLinkHandler,
  listRelayLinksByDroneHandler,
  listRelayLinksByRelayHandler,
  listRelayLinksHandler,
  revokeRelayLinkHandler,
} from "./relay-links.controller";

export const relayLinksRoutes = Router();

relayLinksRoutes.post("/", (req, res, next) => {
  createRelayLinkHandler(req, res).catch(next);
});

relayLinksRoutes.get("/", (req, res, next) => {
  listRelayLinksHandler(req, res).catch(next);
});

relayLinksRoutes.get("/by-relay", (req, res, next) => {
  listRelayLinksByRelayHandler(req, res).catch(next);
});

relayLinksRoutes.get("/by-drone", (req, res, next) => {
  listRelayLinksByDroneHandler(req, res).catch(next);
});

relayLinksRoutes.delete("/:id", (req, res, next) => {
  revokeRelayLinkHandler(req, res).catch(next);
});