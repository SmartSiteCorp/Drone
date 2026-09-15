import type { Server } from "socket.io";
import { onConnection } from "./handlers/connection";
import { registerTelemetryHandlers } from "./handlers/telemetry";
import { registerCommandHandlers } from "./handlers/commands";
import { registerMissionHandlers } from "./handlers/missions";

export function registerSocketHandlers(io: Server) {
  io.on("connection", (socket) => {
    onConnection(io, socket).catch((err) => {
      console.error("Erreur dans onConnection:", err);
      socket.disconnect(true);
    });

    registerTelemetryHandlers(io, socket);
    registerCommandHandlers(io, socket);
    registerMissionHandlers(io, socket);
  });
}
