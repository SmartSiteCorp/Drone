import type { Server, Socket } from "socket.io";
import { pool } from "../db/pool";
import { getKeyPrefix, verifyApiKey } from "../modules/auth/apiKeys.crypto";

type DbRow = {
  api_key_id: string;
  device_id: string;
  key_hash: string;
  scopes: string[];
  revoked_at: string | null;
  expires_at: string | null;
};

function getApiKeyFromSocket(socket: Socket): string | null {
  // 1) recommandé: handshake.auth
  const authKey = socket.handshake.auth?.apiKey;
  if (typeof authKey === "string" && authKey.length > 0) return authKey;

  // 2) fallback: header (utile en test)
  const headerKey = socket.handshake.headers["x-api-key"];
  if (typeof headerKey === "string" && headerKey.length > 0) return headerKey;

  return null;
}

export function useApiKeyAuth(io: Server) {
  io.use(async (socket, next) => {
    try {
      const apiKey = getApiKeyFromSocket(socket);
      if (!apiKey) return next(new Error("Missing apiKey"));

      const keyPrefix = getKeyPrefix(apiKey);

      const r = await pool.query<DbRow>(
        `SELECT
           ak.id as api_key_id,
           ak.key_hash,
           ak.scopes,
           ak.revoked_at,
           ak.expires_at,
           d.id as device_id
         FROM api_keys ak
         JOIN devices d ON d.id = ak.device_id
         WHERE ak.key_prefix = $1
         ORDER BY ak.created_at DESC
         LIMIT 5`,
        [keyPrefix],
      );

      if (r.rowCount === 0) return next(new Error("Unauthorized"));

      const now = new Date();

      for (const row of r.rows) {
        if (row.revoked_at) continue;
        if (row.expires_at && new Date(row.expires_at) <= now) continue;

        const ok = verifyApiKey(apiKey, row.key_hash);
        if (!ok) continue;

        // succès: on met le contexte auth dans socket.data
        socket.data.auth = {
          deviceId: row.device_id,
          apiKeyId: row.api_key_id,
          scopes: row.scopes ?? [],
        };

        // best effort: last_used_at
        pool
          .query(`UPDATE api_keys SET last_used_at = now() WHERE id = $1`, [
            row.api_key_id,
          ])
          .catch(() => {});

        return next();
      }

      return next(new Error("Unauthorized"));
    } catch (e) {
      return next(e as Error);
    }
  });
}
