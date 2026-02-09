import type { Server } from "socket.io";
import { onConnection } from "./handlers/connection";
import { registerTelemetryHandlers } from "./handlers/telemetry";
import { registerCommandHandlers } from "./handlers/commands";

export function registerSocketHandlers(io: Server) {
  io.on("connection", (socket) => {
    onConnection(io, socket);
    registerTelemetryHandlers(io, socket);
    registerCommandHandlers(io, socket);
  });
}
