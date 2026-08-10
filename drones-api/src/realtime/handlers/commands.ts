// server/socket/commands.ts
import type { Server, Socket } from "socket.io";
import { roomDevice } from "../rooms";
import { getActiveRelayForDrone } from "../../modules/relay-links/relay-links.service";

type CommandLabel = "ARM" | "DISARM" | "Mission Auto" | "Loiter" | "RTL" | "Land" | "Stop";

type CommandRequest = {
  label: CommandLabel;
  droneId: string; // ✅ Le dashboard envoie le droneId
};

type CommandAck =
  | { ok: true; commandId: string; acceptedAt: number }
  | { ok: false; error: string };

const ALLOWED: Record<CommandLabel, true> = {
  "ARM": true,
  "DISARM": true,
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

export function registerCommandHandlers(io: Server, socket: Socket) {
  const handleCommand = async (payload: unknown, ack?: (res: CommandAck) => void) => {
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

        // Validation du payload
        if (typeof payload !== "object" || !payload) {
          ack?.({ ok: false, error: "Payload invalide" });
          return;
        }

        const { label, droneId } = payload as any;

        if (!isCommandLabel(label)) {
          ack?.({ ok: false, error: "Commande invalide" });
          return;
        }

        if (!droneId) {
          ack?.({ ok: false, error: "droneId manquant" });
          return;
        }

        // ✅ Résolution du relay pour ce drone
        const relayId = await getActiveRelayForDrone(droneId);
        
        if (!relayId) {
          ack?.({ ok: false, error: "Aucun relay actif pour ce drone" });
          return;
        }

        const commandId = `cmd_${Date.now()}_${Math.random().toString(16).slice(2)}`;

        // ACK immédiat
        ack?.({ ok: true, commandId, acceptedAt: Date.now() });

        // ✅ Envoi vers la room du relay
        await dispatchToDroneRelay(io, {
          commandId,
          label,
          droneId,
          relayId,
          requestedBy: socket.id,
        });

        // statut au demandeur
        socket.emit("commande:status", {
          commandId,
          status: "sent_to_relay",
          droneId,
          relayId,
          ts: Date.now(),
        });
      } catch (err) {
        console.error("Erreur dans commande:send:", err);
        ack?.({ ok: false, error: "Erreur serveur" });
      }
  };

  socket.on("commande:send", handleCommand);

  socket.once("disconnect", () => {
    socket.off("commande:send", handleCommand);
    lastCmdAt.delete(socket.id);
  });
}

async function dispatchToDroneRelay(
  io: Server,
  data: { 
    commandId: string; 
    label: CommandLabel; 
    droneId: string;    // ✅ Le drone cible
    relayId: string;    // ✅ Le relay qui va transmettre
    requestedBy: string;
  }
) {
  // ✅ Envoi vers la room du relay
  io.to(roomDevice(data.relayId)).emit("relay:command", {
    commandId: data.commandId,
    label: data.label,
    droneId: data.droneId,  // Le relay saura quel drone commander
    requestedBy: data.requestedBy,
  });
}
