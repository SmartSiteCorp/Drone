import type { Server, Socket } from "socket.io";
import { roomDevice } from "../rooms";
import { getActiveRelayForDrone } from "../../modules/relay-links/relay-links.service";

type CommandLabel =
  | "ARM"
  | "DISARM"
  | "Mission Auto"
  | "Loiter"
  | "RTL"
  | "Land"
  | "Stop"
  | "MOTOR_TEST";

type CommandRequest = {
  label: CommandLabel;
  droneId: string;
  percent?: number;
  durationSeconds?: number;
  motor?: number | "ALL";
};

type CommandAck =
  | { ok: true; commandId: string; acceptedAt: number }
  | { ok: false; error: string };

const ALLOWED: Record<CommandLabel, true> = {
  ARM: true,
  DISARM: true,
  "Mission Auto": true,
  Loiter: true,
  RTL: true,
  Land: true,
  Stop: true,
  MOTOR_TEST: true,
};

function isCommandLabel(x: unknown): x is CommandLabel {
  return typeof x === "string" && (x as CommandLabel) in ALLOWED;
}

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
  const handleCommand = async (
    payload: unknown,
    ack?: (res: CommandAck) => void,
  ) => {
    try {
      if (!rateLimit(socket)) {
        ack?.({ ok: false, error: "Rate limit" });
        return;
      }

      if (!hasScope(socket, "commands:write")) {
        ack?.({
          ok: false,
          error: "Permission refusée (commands:write requis)",
        });
        return;
      }

      if (typeof payload !== "object" || !payload) {
        ack?.({ ok: false, error: "Payload invalide" });
        return;
      }

      const { label, droneId, percent, durationSeconds, motor } =
        payload as CommandRequest;

      if (!isCommandLabel(label)) {
        ack?.({ ok: false, error: "Commande invalide" });
        return;
      }

      if (!droneId) {
        ack?.({ ok: false, error: "droneId manquant" });
        return;
      }

      if (
        label === "MOTOR_TEST" &&
        (typeof percent !== "number" ||
          !Number.isFinite(percent) ||
          percent < 0 ||
          percent > 100)
      ) {
        ack?.({ ok: false, error: "percent doit être compris entre 0 et 100" });
        return;
      }

      if (
        label === "MOTOR_TEST" &&
        (typeof durationSeconds !== "number" ||
          !Number.isFinite(durationSeconds) ||
          durationSeconds <= 0)
      ) {
        ack?.({ ok: false, error: "durationSeconds doit être supérieur à 0" });
        return;
      }

      if (
        label === "MOTOR_TEST" &&
        motor !== undefined &&
        motor !== "ALL" &&
        (!Number.isInteger(motor) || motor < 1 || motor > 4)
      ) {
        ack?.({
          ok: false,
          error: "motor doit être ALL ou un numéro entre 1 et 4",
        });
        return;
      }

      const relayId = await getActiveRelayForDrone(droneId);

      if (!relayId) {
        ack?.({ ok: false, error: "Aucun relay actif pour ce drone" });
        return;
      }

      const commandId = `cmd_${Date.now()}_${Math.random().toString(16).slice(2)}`;

      ack?.({ ok: true, commandId, acceptedAt: Date.now() });

      await dispatchToDroneRelay(io, {
        commandId,
        label,
        droneId,
        relayId,
        requestedBy: socket.id,
        percent: label === "MOTOR_TEST" ? percent : undefined,
        durationSeconds: label === "MOTOR_TEST" ? durationSeconds : undefined,
        motor: label === "MOTOR_TEST" ? (motor ?? "ALL") : undefined,
      });

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
    droneId: string;
    relayId: string;
    requestedBy: string;
    percent?: number;
    durationSeconds?: number;
    motor?: number | "ALL";
  },
) {
  io.to(roomDevice(data.relayId)).emit("relay:command", {
    commandId: data.commandId,
    label: data.label,
    droneId: data.droneId,
    requestedBy: data.requestedBy,
    ...(data.label === "MOTOR_TEST"
      ? {
          percent: data.percent,
          durationSeconds: data.durationSeconds,
          motor: data.motor ?? "ALL",
        }
      : {}),
  });
}
