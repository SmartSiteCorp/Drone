import type { NextFunction, Request, Response } from "express";
import { pool } from "../../db/pool";
import { getKeyPrefix, verifyApiKey } from "../auth/apiKeys.crypto";
import { getActiveRelayForDrone } from "../relay-links/relay-links.service";
import { getIO } from "../../realtime/io";
import { roomDevice } from "../../realtime/rooms";
import {
  createCameraStreamToken,
  getCameraStreamDroneId,
} from "./video.service";

type ApiKeyRow = {
  api_key_id: string;
  key_hash: string;
  scopes: string[];
  revoked_at: string | null;
  expires_at: string | null;
  device_id: string;
  device_type: string;
};

type MediaMTXAuthRequest = {
  user?: string;
  password?: string;
  token?: string;
  action?: string;
  path?: string;
  protocol?: string;
};

async function findApiKey(apiKey: string): Promise<ApiKeyRow | null> {
  const result = await pool.query<ApiKeyRow>(
    `SELECT ak.id AS api_key_id, ak.key_hash, ak.scopes,
            ak.revoked_at, ak.expires_at, d.id AS device_id,
            d.type AS device_type
     FROM api_keys ak
     JOIN devices d ON d.id = ak.device_id
     WHERE ak.key_prefix = $1
     ORDER BY ak.created_at DESC
     LIMIT 5`,
    [getKeyPrefix(apiKey)],
  );

  const now = new Date();
  const row = result.rows.find((candidate) =>
    !candidate.revoked_at &&
    (!candidate.expires_at || new Date(candidate.expires_at) > now) &&
    verifyApiKey(apiKey, candidate.key_hash),
  );

  if (row) {
    pool
      .query(`UPDATE api_keys SET last_used_at = now() WHERE id = $1`, [row.api_key_id])
      .catch(() => {});
  }

  return row ?? null;
}

export function requireVideoScope(scope: string, deviceType: string) {
  return async (req: Request, res: Response, next: NextFunction) => {
    try {
      const apiKey = req.header("x-api-key");
      if (!apiKey) {
        return res.status(401).json({ error: "Missing x-api-key" });
      }

      const row = await findApiKey(apiKey);

      if (!row || row.device_type !== deviceType || !(row.scopes ?? []).includes(scope)) {
        return res.status(403).json({ error: `Valid ${deviceType} key with ${scope} scope required` });
      }

      res.locals.videoDeviceId = row.device_id;
      return next();
    } catch (error) {
      return next(error);
    }
  };
}

export async function mediaMTXAuthHandler(req: Request, res: Response) {
  const auth = req.body as MediaMTXAuthRequest;
  const path = auth.path ?? "";
  const droneId = path.startsWith("drone/") ? path.slice("drone/".length) : "";

  if (auth.action === "publish" && auth.protocol === "rtsp" && auth.user === "relay" && auth.password && droneId) {
    const row = await findApiKey(auth.password);
    const linkedRelayId = await getActiveRelayForDrone(droneId);
    if (
      row?.device_type === "relay" &&
      (row.scopes ?? []).includes("telemetry:write") &&
      linkedRelayId === row.device_id
    ) {
      return res.sendStatus(204);
    }
  }

  if (auth.action === "read") {
    const token = auth.token || auth.password;
    if (token && getCameraStreamDroneId(token) === droneId) {
      return res.sendStatus(204);
    }
  }

  return res.sendStatus(401);
}

export async function requestCameraStreamHandler(
  req: Request,
  res: Response,
  action: "start" | "stop",
) {
  const droneId = Array.isArray(req.params.droneId) ? req.params.droneId[0] : req.params.droneId;
  const relayId = await getActiveRelayForDrone(droneId);
  if (!relayId) {
    return res.status(409).json({ error: "No active relay for this drone" });
  }

  const io = getIO();
  const relayRoom = roomDevice(relayId);
  if ((io.sockets.adapter.rooms.get(relayRoom)?.size ?? 0) === 0) {
    return res.status(409).json({ error: "Active relay is offline" });
  }

  io.to(relayRoom).emit(`relay:video:${action}`, { droneId });
  return res.status(202).json({ ok: true, action, droneId, relayId });
}

export async function createCameraStreamTokenHandler(req: Request, res: Response) {
  const droneId = Array.isArray(req.params.droneId) ? req.params.droneId[0] : req.params.droneId;
  const drone = await pool.query(`SELECT 1 FROM devices WHERE id = $1 AND type = 'drone'`, [droneId]);
  if (!drone.rowCount) {
    return res.status(404).json({ error: "Drone not found" });
  }

  const { token, expiresInSeconds } = createCameraStreamToken(droneId);
  const path = `drone/${encodeURIComponent(droneId)}`;
  const webRtcBaseUrl = (process.env.MEDIAMTX_WEBRTC_URL ?? "http://localhost:8889").replace(/\/$/, "");
  const hlsBaseUrl = (process.env.MEDIAMTX_HLS_URL ?? "http://localhost:8888").replace(/\/$/, "");
  return res.status(201).json({
    token,
    expiresInSeconds,
    path: droneId,
    playerUrl: `${webRtcBaseUrl}/${path}`,
    whepUrl: `${webRtcBaseUrl}/${path}/whep`,
    hlsPlayerUrl: `${hlsBaseUrl}/${path}`,
    hlsUrl: `${hlsBaseUrl}/${path}/index.m3u8`,
  });
}
