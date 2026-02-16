// server/socket/commands.ts
import type { Server, Socket } from "socket.io";
import { roomDevice } from "../rooms";

type CommandLabel = "Démarrer" | "Mission Auto" | "Loiter" | "RTL" | "Land" | "Stop";

type CommandRequest =
  | CommandLabel
  | {
      label: CommandLabel;
      deviceID?: string; // relay ciblé
    };

type CommandAck =
  | { ok: true; commandId: string; acceptedAt: number }
  | { ok: false; error: string };

const ALLOWED: Record<CommandLabel, true> = {
  "Démarrer": true,
  "Mission Auto": true,
  "Loiter": true,
  "RTL": true,
  "Land": true,
  "Stop": true,
};

function isCommandLabel(x: unknown): x is CommandLabel {
  return typeof x === "string" && (x as CommandLabel) in ALLOWED;
}

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

export function registerCommandHandlers(io: Server) {
  io.on("connection", (socket) => {
    socket.on("commande:send", async (payload: unknown, ack?: (res: CommandAck) => void) => {
      try {
        if (!rateLimit(socket)) {
          ack?.({ ok: false, error: "Rate limit" });
          return;
        }

        // ✅ (optionnel mais recommandé) seuls les dashboards autorisés peuvent envoyer
        if (!hasScope(socket, "commands:write")) {
          ack?.({ ok: false, error: "Permission refusée (commands:write requis)" });
          return;
        }

        // payload peut être "RTL" ou {label, droneId}
        const label = typeof payload === "string" ? payload : (payload as any)?.label;
        if (!isCommandLabel(label)) {
          ack?.({ ok: false, error: "Commande invalide" });
          return;
        }

        // deviceID (relay ciblé)
        const deviceID =
          (typeof payload === "object" && payload ? (payload as any).deviceID : undefined) ??
          socket.data.auth?.deviceID; // fallback pratique si mono-drone

        if (!deviceID) {
          ack?.({ ok: false, error: "deviceID manquant" });
          return;
        }

        const commandId = `cmd_${Date.now()}_${Math.random().toString(16).slice(2)}`;

        // ACK immédiat
        ack?.({ ok: true, commandId, acceptedAt: Date.now() });

        // ✅ Envoi vers la room du deviceId (le relay du drone est dedans)
        await dispatchToDroneRelay(io, {
          commandId,
          label,
          deviceID: deviceID,
          requestedBy: socket.id,
        });

        // statut au demandeur
        socket.emit("commande:status", {
          commandId,
          status: "sent_to_relay",
          deviceID: deviceID,
          ts: Date.now(),
        });
      } catch {
        ack?.({ ok: false, error: "Erreur serveur" });
      }
    });
  });
}

async function dispatchToDroneRelay(
  io: Server,
  data: { commandId: string; label: CommandLabel; deviceID: string; requestedBy: string }
) {
  // ✅ même convention partout : roomDevice(deviceID)
  io.to(roomDevice(data.deviceID)).emit("relay:command", data);
}
