import type { Server, Socket } from "socket.io";
import { roomDevice } from "../rooms";

type CommandPayload = {
  relayId: string;        // à qui envoyer
  droneId?: string;
  command: "RTL" | "LOITER" | "TAKEOFF" | "LAND";
  params?: Record<string, unknown>;
};

export function registerCommandHandlers(io: Server, socket: Socket) {
  socket.on("command:send", (payload: CommandPayload) => {
    if (!payload?.relayId || !payload?.command) return;

    // Forward vers le boîtier relay cible
    io.to(roomDevice(payload.relayId)).emit("command:execute", payload);

    socket.emit("command:queued", { ok: true });
  });

  // Le relay s’enregistre / rejoint sa room
  socket.on("relay:register", ({ relayId }: { relayId: string }) => {
    if (!relayId) return;
    socket.join(roomDevice(relayId));
    socket.emit("relay:registered", { relayId });
  });
}
