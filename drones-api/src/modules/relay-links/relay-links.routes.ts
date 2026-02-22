import { Router } from "express";
import { createRelayLinkHandler } from "./relay-links.controller";

export const relayLinksRoutes = Router();

relayLinksRoutes.post("/", (req, res, next) => {
  createRelayLinkHandler(req, res).catch(next);
});