import type { Server, Socket } from "socket.io";
import { roomDevice } from "../rooms";
import { logger } from "../../core/logger";

export function onConnection(_io: Server, socket: Socket) {
  const auth = socket.data.auth; // vient du middleware API key

  logger.info("Socket connected", { socketId: socket.id, deviceId: auth?.deviceId, scopes: auth?.scopes });

  if (auth?.deviceId) {
    logger.info("Joining device room", { socketId: socket.id, deviceId: auth.deviceId });
    socket.join(roomDevice(auth.deviceId));
    logger.info("Joined device room", { socketId: socket.id, deviceId: auth.deviceId });
  }

  // envoie un message de bienvenue avec les infos d'authentification
  setTimeout(() => {
    socket.emit("connected", {
      ok: true,
      deviceId: auth?.deviceId,
      scopes: auth?.scopes,
    });
  }, 200);

  socket.on("disconnect", (reason) => {
    logger.info("Socket disconnected", { socketId: socket.id, reason });
  });
}
