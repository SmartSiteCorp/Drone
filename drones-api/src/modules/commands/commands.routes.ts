import { Router } from "express";
import { requireCommandsWriteScope } from "./commands.auth";
import { sendCommandHandler } from "./commands.controller";

export const commandsRoutes = Router();

commandsRoutes.post("/send", requireCommandsWriteScope, (req, res, next) => {
  sendCommandHandler(req, res).catch(next);
});
