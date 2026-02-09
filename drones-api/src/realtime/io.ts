import { Server } from "socket.io";
import type http from "http";

export function createIO(server: http.Server) {
  const io = new Server(server, {
    cors: {
      origin: true,
      credentials: true,
    },
  });

  return io;
}
