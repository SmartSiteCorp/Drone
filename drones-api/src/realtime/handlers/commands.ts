import type { Server, Socket } from "socket.io";
import { SendCommandSchema } from "../../modules/commands/commands.schemas";
import { sendCommandToDrone } from "../../modules/commands/commands.service";

type CommandAck =
  | { ok: true; commandId: string; acceptedAt: number }
  | { ok: false; error: string };

// Anti-spam simple (par socket)
const lastCmdAt = new Map<string, number>();
const MIN_INTERVAL_MS = 700;

function rateLimit(socket: Socket): boolean {
  const now = Date.now();
  const last = lastCmdAt.get(socket.id) ?? 0;
  if (now - last < MIN_INTERVAL_MS) return false;
  lastCmdAt.set(socket.id, now);
  return true;
}

function hasScope(socket: Socket, scope: string): boolean {
  const scopes: string[] = socket.data.auth?.scopes ?? socket.data.scopes ?? [];
  return scopes.includes(scope);
}

export function registerCommandHandlers(_io: Server, socket: Socket) {
  socket.on(
    "commande:send",
    async (payload: unknown, ack?: (res: CommandAck) => void) => {
      try {
        if (!rateLimit(socket)) {
          ack?.({ ok: false, error: "Rate limit" });
          return;
        }

        if (!hasScope(socket, "commands:write")) {
          ack?.({ ok: false, error: "Permission refusée (commands:write requis)" });
          return;
        }

        const parsed = SendCommandSchema.safeParse(payload);
        if (!parsed.success) {
          ack?.({ ok: false, error: "Payload invalide" });
          return;
        }

        const result = await sendCommandToDrone({
          ...parsed.data,
          requestedBy: socket.id,
        });

        ack?.({
          ok: true,
          commandId: result.commandId,
          acceptedAt: result.acceptedAt,
        });

        socket.emit("commande:status", {
          commandId: result.commandId,
          status: "sent_to_relay",
          droneId: result.droneId,
          relayId: result.relayId,
          ts: Date.now(),
        });
      } catch (err) {
        if (err instanceof Error && err.message === "NO_ACTIVE_RELAY") {
          ack?.({ ok: false, error: "Aucun relay actif pour ce drone" });
          return;
        }

        console.error("Erreur dans commande:send:", err);
        ack?.({ ok: false, error: "Erreur serveur" });
      }
    },
  );
}
