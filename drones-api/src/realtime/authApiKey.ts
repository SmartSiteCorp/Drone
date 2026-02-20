import type { Server, Socket } from "socket.io";
import { pool } from "../db/pool";
import { getKeyPrefix, verifyApiKey } from "../modules/auth/apiKeys.crypto";
import { logger } from "../core/logger";
import { log } from "node:console";

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
      logger.info("[sio] Tentative de connexion depuis l'id:", { socketId: socket.id });
      console.log("[sio] Tentative de connexion depuis l'id:", socket.id);

      const apiKey = getApiKeyFromSocket(socket);
      if (!apiKey) {
        logger.warn("[sio] apiKey manquante pour la socket id:", socket.id);
        console.warn("[sio] apiKey manquante pour la socket id:", socket.id);
        return next(new Error("Missing apiKey"));
      }

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

      if (r.rowCount === 0) { 
        console.warn("[sio] apiKey non trouvée pour le préfixe:", keyPrefix + " (socket id: " + socket.id + ")");
        return next(new Error("Unauthorized"));
      }

      const now = new Date();

      for (const row of r.rows) {
        if (row.revoked_at) { 
          logger.warn("[sio] apiKey révoquée (id:", row.api_key_id + ", socket id: " + socket.id + ")");
          console.warn("[sio] apiKey révoquée (id:", row.api_key_id + ", socket id: " + socket.id + ")");
          continue;}
        if (row.expires_at && new Date(row.expires_at) <= now) {
          logger.warn("[sio] apiKey expirée (id:", row.api_key_id + ", socket id: " + socket.id + ")");
          console.warn("[sio] apiKey expirée (id:", row.api_key_id + ", socket id: " + socket.id + ")");
          continue;
        }

        const ok = verifyApiKey(apiKey, row.key_hash);
        if (!ok) {
          logger.warn("[sio] apiKey invalide (id:", row.api_key_id + ", socket id: " + socket.id + ")");
          console.warn("[sio] apiKey invalide (id:", row.api_key_id + ", socket id: " + socket.id + ")");
          continue;
        }

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
      logger.warn("[sio] Aucune apiKey valide trouvée pour la socket id: " + socket.id);
      return next(new Error("Unauthorized"));
    } catch (e) {
      logger.error("Erreur interne dans le middleware Socket.IO d'authentification", e);
      return next(e as Error);
    }
  });
}
