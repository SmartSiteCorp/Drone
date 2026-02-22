import type { Server, Socket } from "socket.io";
import { getAllowedDroneIdsForRelay } from "../../modules/relay-links/relay-links.service";
import { roomDevice } from "../rooms";
import { logger } from "../../core/logger";

export async function onConnection(_io: Server, socket: Socket) {
  const auth = socket.data.auth; // vient du middleware API key

  logger.info("Socket connected", { socketId: socket.id, deviceId: auth?.deviceId, scopes: auth?.scopes });

  if (auth?.deviceId) {
    logger.info("Joining device room", { socketId: socket.id, deviceId: auth.deviceId });
    socket.join(roomDevice(auth.deviceId));
    logger.info("Joined device room", { socketId: socket.id, deviceId: auth.deviceId });
  }

   if (auth?.deviceType === "relay") {
    const ids = await getAllowedDroneIdsForRelay(auth.deviceId);
    socket.data.allowedDroneIds = new Set(ids);
  }

  // envoie un message de bienvenue avec les infos d'authentification

  socket.emit("connected", {
    ok: true,
    deviceId: auth?.deviceId,
    deviceType: auth?.deviceType,
    scopes: auth?.scopes,
    allowedDroneIds:
      auth?.deviceType === "relay"
        ? Array.from(socket.data.allowedDroneIds ?? [])
        : undefined,
  });

  socket.on("disconnect", (reason) => {
    logger.info("Socket disconnected", { socketId: socket.id, reason });
  });
}
