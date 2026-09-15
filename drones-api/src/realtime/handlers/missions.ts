import type { Server, Socket } from "socket.io";

import { roomDevice } from "../rooms";
import { getActiveRelayForDrone } from "../../modules/relay-links/relay-links.service";
import {
  parseMissionFile,
  type MissionItem,
} from "../../modules/missions/mission.parser";

type MissionUploadRequest = {
  droneId: string;
  filename: string;
  content: string;
};

type MissionUploadAck =
  | {
      ok: true;
      missionId: string;
      itemCount: number;
      acceptedAt: number;
    }
  | {
      ok: false;
      error: string;
    };

function hasScope(socket: Socket, scope: string): boolean {
  const scopes: string[] =
    socket.data.auth?.scopes ??
    socket.data.scopes ??
    [];

  return scopes.includes(scope);
}

const MAX_MISSION_SIZE = 1024 * 1024; // 1 Mo
const MAX_MISSION_ITEMS = 1000;

export function registerMissionHandlers(
  io: Server,
  socket: Socket,
) {
  socket.on(
    "mission:upload",
    async (
      payload: MissionUploadRequest,
      ack?: (response: MissionUploadAck) => void,
    ) => {
      try {
        // Pour commencer on réutilise le droit commands:write.
        if (!hasScope(socket, "commands:write")) {
          ack?.({
            ok: false,
            error:
              "Permission refusée (commands:write requis)",
          });
          return;
        }

        if (!payload || typeof payload !== "object") {
          ack?.({
            ok: false,
            error: "Payload invalide",
          });
          return;
        }

        const { droneId, filename, content } = payload;

        if (!droneId || typeof droneId !== "string") {
          ack?.({
            ok: false,
            error: "droneId manquant",
          });
          return;
        }

        if (!filename || typeof filename !== "string") {
          ack?.({
            ok: false,
            error: "filename manquant",
          });
          return;
        }

        if (typeof content !== "string") {
          ack?.({
            ok: false,
            error: "content manquant",
          });
          return;
        }

        if (
          Buffer.byteLength(content, "utf8") >
          MAX_MISSION_SIZE
        ) {
          ack?.({
            ok: false,
            error: "Fichier mission trop volumineux",
          });
          return;
        }

        let items: MissionItem[];

        try {
          items = parseMissionFile(filename, content);
        } catch (error) {
          ack?.({
            ok: false,
            error:
              error instanceof Error
                ? error.message
                : "Mission invalide",
          });
          return;
        }

        if (items.length > MAX_MISSION_ITEMS) {
          ack?.({
            ok: false,
            error: `Mission trop longue (${MAX_MISSION_ITEMS} items maximum)`,
          });
          return;
        }

        const relayId =
          await getActiveRelayForDrone(droneId);

        if (!relayId) {
          ack?.({
            ok: false,
            error:
              "Aucun relay actif pour ce drone",
          });
          return;
        }

        const missionId =
          `mission_${Date.now()}_${Math.random()
            .toString(16)
            .slice(2)}`;

        io.to(roomDevice(relayId)).emit(
          "relay:mission:upload",
          {
            missionId,
            droneId,
            filename,
            items,
            requestedBy: socket.id,
          },
        );

        ack?.({
          ok: true,
          missionId,
          itemCount: items.length,
          acceptedAt: Date.now(),
        });

        socket.emit("mission:status", {
          missionId,
          droneId,
          relayId,
          status: "sent_to_relay",
          itemCount: items.length,
          ts: Date.now(),
        });
      } catch (error) {
        console.error(
          "[mission] upload error:",
          error,
        );

        ack?.({
          ok: false,
          error: "Erreur serveur",
        });
      }
    },
  );
}