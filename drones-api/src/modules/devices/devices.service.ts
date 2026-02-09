import { pool } from "../../db/pool";
import type { CreateDeviceInput } from "./devices.schemas";
import { generateApiKey, getKeyPrefix, hashApiKey } from "../auth/apiKeys.crypto";

function defaultScopes(type: CreateDeviceInput["type"]): string[] {
  switch (type) {
    case "relay":
      return ["telemetry:write", "commands:read"];
    case "dashboard":
      return ["telemetry:read", "commands:write"];
    case "admin":
      return ["devices:manage", "keys:manage"];
  }
}

export async function createDevice(input: CreateDeviceInput) {
  const apiKey = generateApiKey();
  const keyPrefix = getKeyPrefix(apiKey);
  const keyHash = hashApiKey(apiKey);
  const scopes = input.scopes?.length ? input.scopes : defaultScopes(input.type);

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const deviceRes = await client.query(
      `INSERT INTO devices (name, type)
       VALUES ($1, $2)
       RETURNING id, name, type, created_at`,
      [input.name, input.type]
    );

    const device = deviceRes.rows[0];

    const keyRes = await client.query(
      `INSERT INTO api_keys (device_id, key_prefix, key_hash, scopes)
       VALUES ($1, $2, $3, $4)
       RETURNING id, key_prefix, scopes, created_at`,
      [device.id, keyPrefix, keyHash, scopes]
    );

    const apiKeyRow = keyRes.rows[0];

    await client.query("COMMIT");

    // IMPORTANT: on renvoie la clé EN CLAIR UNE SEULE FOIS ici.
    return {
      device,
      apiKey: {
        id: apiKeyRow.id,
        keyPrefix: apiKeyRow.key_prefix,
        scopes: apiKeyRow.scopes,
        createdAt: apiKeyRow.created_at,
        // la vraie clé en clair, à afficher/retourner UNE FOIS au boîtier
        value: apiKey,
      },
    };
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
}
