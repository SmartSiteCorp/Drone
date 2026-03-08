import { Server } from "socket.io";
import type http from "http";

let ioInstance: Server | null = null;

export function createIO(server: http.Server) {
  const io = new Server(server, {
    cors: {
      origin: true,
      credentials: true,
    },
  });

  ioInstance = io;
  return io;
}

export function getIO(): Server {
  if (!ioInstance) {
    throw new Error("Socket.IO instance not initialized. Call createIO() first.");
  }
  return ioInstance;
}
