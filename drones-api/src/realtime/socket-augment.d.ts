import type { SocketAuthContext } from "./realtime/types";

declare module "socket.io" {
  interface Socket {
    data: {
      auth?: SocketAuthContext;
    };
  }
}

export {};
