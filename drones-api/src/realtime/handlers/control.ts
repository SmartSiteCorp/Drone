import { randomUUID } from "node:crypto";
import { performance } from "node:perf_hooks";
import type { Server, Socket } from "socket.io";
import { z } from "zod";
import { roomDevice } from "../rooms";
import { getActiveRelayForDrone } from "../../modules/relay-links/relay-links.service";

const TIMEOUT_MS = 1500;

const StartSchema = z.object({
  droneId: z.string().uuid(),
});

const AxesSchema = z.object({
  sessionId: z.string().uuid(),
  seq: z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER),
  forward: z.number().min(-1).max(1),
  right: z.number().min(-1).max(1),
  vertical: z.number().min(-1).max(1),
  yaw: z.number().min(-1).max(1),
});

const StopSchema = z.object({
  sessionId: z.string().uuid(),
});

type Ack = (result:
  | { ok: true; sessionId?: string; droneId?: string }
  | { ok: false; error: string }
) => void;

type Session = {
  id: string;
  droneId: string;
  relayId: string;
  socket: Socket;
  lastSeq: number;
  deadline: number;
  timer?: ReturnType<typeof setTimeout>;
};

// Valable pour une seule instance de l’API.
const sessionsByDrone = new Map<string, Session>();

function hasPermission(socket: Socket) {
  const scopes: string[] =
    socket.data.auth?.scopes ?? socket.data.scopes ?? [];

  return scopes.includes("commands:write");
}

export function registerControlHandlers(io: Server, socket: Socket) {
  let session: Session | undefined;
  let starting = false;
  let generation = 0;

  const relayOnline = (relayId: string) =>
    (io.sockets.adapter.rooms.get(roomDevice(relayId))?.size ?? 0) > 0;

  function finish(reason: string) {
    const current = session;
    if (!current) return;

    session = undefined;
    clearTimeout(current.timer);

    if (sessionsByDrone.get(current.droneId) === current) {
      sessionsByDrone.delete(current.droneId);
    }

    // Message terminal : le relay doit neutraliser les axes
    // et invalider cette session.
    io.to(roomDevice(current.relayId)).emit("relay:control:stop", {
      sessionId: current.id,
      droneId: current.droneId,
      reason,
    });

    socket.emit("drone:control:ended", {
      sessionId: current.id,
      reason,
    });
  }

  function checkTimeout(current: Session) {
    if (session !== current) return;

    const remaining = current.deadline - performance.now();

    if (remaining <= 0) {
      finish("timeout");
      return;
    }

    current.timer = setTimeout(() => checkTimeout(current), remaining);
  }

  socket.on(
    "drone:control:start",
    async (payload: unknown, ack?: Ack) => {
      const reply = (result: Parameters<Ack>[0]) => {
        if (typeof ack === "function") ack(result);
      };

      if (!hasPermission(socket)) {
        reply({ ok: false, error: "commands:write requis" });
        return;
      }

      const parsed = StartSchema.safeParse(payload);
      if (!parsed.success) {
        reply({ ok: false, error: "droneId invalide" });
        return;
      }

      if (starting || session) {
        reply({ ok: false, error: "Session déjà active ou en préparation" });
        return;
      }

      starting = true;
      const attempt = ++generation;

      try {
        const droneId = parsed.data.droneId;
        const relayId = await getActiveRelayForDrone(droneId);

        // Un stop ou une déconnexion pendant la requête annule le départ.
        if (!socket.connected || attempt !== generation) return;

        if (!relayId || !relayOnline(relayId)) {
          reply({ ok: false, error: "Relay absent ou déconnecté" });
          return;
        }

        // Vérification après l’attente SQL : deux demandes simultanées
        // ne doivent pas acquérir le même drone.
        if (sessionsByDrone.has(droneId)) {
          reply({ ok: false, error: "Drone déjà contrôlé par un pilote" });
          return;
        }

        const current: Session = {
          id: randomUUID(),
          droneId,
          relayId,
          socket,
          lastSeq: -1,
          deadline: performance.now() + TIMEOUT_MS,
        };

        session = current;
        sessionsByDrone.set(droneId, current);
        checkTimeout(current);

        reply({
          ok: true,
          sessionId: current.id,
          droneId,
        });
      } catch (error) {
        console.error("Erreur préparation contrôle:", error);
        reply({ ok: false, error: "Erreur serveur" });
      } finally {
        starting = false;
      }
    },
  );

  socket.on("drone:control", (payload: unknown) => {
    const current = session;
    if (!current) return;

    if (!hasPermission(socket)) {
      finish("permission");
      return;
    }

    const parsed = AxesSchema.safeParse(payload);
    if (!parsed.success) return;

    const data = parsed.data;

    if (data.sessionId !== current.id) return;
    if (data.seq <= current.lastSeq) return;

    // Ne pas réactiver une session expirée avec un paquet tardif.
    if (performance.now() >= current.deadline) {
      finish("timeout");
      return;
    }

    if (!relayOnline(current.relayId)) {
      finish("relay_offline");
      return;
    }

    current.lastSeq = data.seq;
    current.deadline = performance.now() + TIMEOUT_MS;

    // Aucun accès SQL dans cette boucle.
    io.to(roomDevice(current.relayId)).volatile.emit("relay:control", {
      ...data,
      droneId: current.droneId,
    });
  });

  socket.on("drone:control:stop", (payload: unknown) => {
    const parsed = StopSchema.safeParse(payload);
    if (!parsed.success) return;

    if (session?.id === parsed.data.sessionId) {
      ++generation;
      finish("pilot_stop");
    }
  });

  socket.once("disconnect", () => {
    ++generation;
    finish("disconnect");

    // Si le socket déconnecté appartenait à un relay,
    // terminer aussi les sessions qui dépendaient de lui.
    for (const current of [...sessionsByDrone.values()]) {
      if (!relayOnline(current.relayId)) {
        current.socket.emit("drone:control:ended", {
          sessionId: current.id,
          reason: "relay_offline",
        });
        // Leur watchdog libérera la session au plus tard à l’échéance.
      }
    }
  });
}