import type { NextFunction, Request, Response } from "express";
import { pool } from "../../db/pool";
import { getKeyPrefix, verifyApiKey } from "../auth/apiKeys.crypto";

type ApiKeyRow = {
  api_key_id: string;
  key_hash: string;
  scopes: string[];
  revoked_at: string | null;
  expires_at: string | null;
  device_id: string;
  device_type: string;
};

export async function requireCommandsWriteScope(
  req: Request,
  res: Response,
  next: NextFunction,
) {
  try {
    const apiKey = req.header("x-api-key");
    if (!apiKey) {
      return res.status(401).json({ error: "Missing x-api-key" });
    }

    const keyPrefix = getKeyPrefix(apiKey);

    const r = await pool.query<ApiKeyRow>(
      `SELECT
         ak.id as api_key_id,
         ak.key_hash,
         ak.scopes,
         ak.revoked_at,
         ak.expires_at,
         d.id as device_id,
         d.type as device_type
       FROM api_keys ak
       JOIN devices d ON d.id = ak.device_id
       WHERE ak.key_prefix = $1
       ORDER BY ak.created_at DESC
       LIMIT 5`,
      [keyPrefix],
    );

    if (!r.rowCount) {
      return res.status(401).json({ error: "Unauthorized" });
    }

    const now = new Date();

    for (const row of r.rows) {
      if (row.revoked_at) continue;
      if (row.expires_at && new Date(row.expires_at) <= now) continue;
      if (!verifyApiKey(apiKey, row.key_hash)) continue;

      if (!(row.scopes ?? []).includes("commands:write")) {
        return res.status(403).json({ error: "commands:write scope required" });
      }

      pool
        .query(`UPDATE api_keys SET last_used_at = now() WHERE id = $1`, [
          row.api_key_id,
        ])
        .catch(() => {});

      return next();
    }

    return res.status(401).json({ error: "Unauthorized" });
  } catch (error) {
    return next(error);
  }
}
