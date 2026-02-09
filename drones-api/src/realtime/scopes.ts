import type { Socket } from "socket.io";

export function requireScope(socket: Socket, scope: string) {
  const scopes = socket.data.auth?.scopes ?? [];
  if (!scopes.includes(scope)) {
    throw new Error(`Forbidden: missing scope ${scope}`);
  }
}
