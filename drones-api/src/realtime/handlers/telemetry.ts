import type { Server, Socket } from "socket.io";
import { roomDrone } from "../rooms";
import { requireScope } from "../scopes";

type TelemetryPayload = {
  droneId: string;
  ts: number;
  lat?: number;
  lon?: number;
  alt?: number;
  groundspeed?: number;
  mode?: string;
};

export function registerTelemetryHandlers(io: Server, socket: Socket) {
  socket.on("telemetry:push", (payload: TelemetryPayload) => {
    try {
      //  relay seulement
      requireScope(socket, "telemetry:write");

      if (!payload?.droneId || typeof payload.ts !== "number") {
        console.warn("[telemetry] invalid payload", payload);
        socket.emit("app:error", {
          event: "telemetry:push",
          message: "Invalid payload",
          expected: {
            droneId: "string",
            ts: "number",
          },
        });
        return;
      }

      io.to(roomDrone(payload.droneId)).emit("telemetry:update", {
        ...payload,
        sourceDeviceId: socket.data.auth?.deviceId,
      });

      socket.emit("telemetry:push:ack", {
        ok: true,
        droneId: payload.droneId,
        ts: payload.ts,
      });
    } catch (e) {
      socket.emit("app:error", {
        event: "telemetry:push",
        message: (e as Error).message,
      });
    }
  });

  socket.on("telemetry:subscribe", ({ droneId }: { droneId: string }) => {
    try {
      //  dashboard only
      requireScope(socket, "telemetry:read");

      if (!droneId) return;
      socket.join(roomDrone(droneId));
      socket.emit("telemetry:subscribed", { droneId });
    } catch (e) {
      socket.emit("app:error", {
        event: "telemetry:subscribe",
        message: (e as Error).message,
      });
    }
  });

  socket.on("telemetry:unsubscribe", ({ droneId }: { droneId: string }) => {
    try {
      requireScope(socket, "telemetry:read");

      if (!droneId) return;
      socket.leave(roomDrone(droneId));
      socket.emit("telemetry:unsubscribed", { droneId });
    } catch (e) {
      socket.emit("app:error", {
        event: "telemetry:unsubscribe",
        message: (e as Error).message,
      });
    }
  });
}
