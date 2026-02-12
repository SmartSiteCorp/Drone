import type { Server, Socket } from "socket.io";
import { roomDevice } from "../rooms";

export function onConnection(_io: Server, socket: Socket) {
  const auth = socket.data.auth; // vient du middleware API key

  console.log("Socket connected", socket.id, auth?.deviceId, auth?.scopes);

  if (auth?.deviceId) {
    socket.join(roomDevice(auth.deviceId));
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
    console.log("Socket disconnected", socket.id, reason);
  });
}
