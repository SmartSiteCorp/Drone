import { pool } from "../../db/pool";
import type { CreateDeviceInput } from "./devices.schemas";
import {
  generateApiKey,
  getKeyPrefix,
  hashApiKey,
} from "../auth/apiKeys.crypto";
import { toDevice, type DeviceRow } from "./devices.mapper";
import { defaultScopesForDevice } from "../auth/scopes";
import { Device } from "./devices.model";
import { getIO } from "../../realtime/io";
import { roomDevice } from "../../realtime/rooms";
import { logger } from "../../core/logger";

export async function createDevice(input: CreateDeviceInput) {
  const apiKey = generateApiKey();
  const keyPrefix = getKeyPrefix(apiKey);
  const keyHash = hashApiKey(apiKey);

  const scopes = input.scopes?.length
    ? input.scopes
    : defaultScopesForDevice(input.type);

  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const deviceRes = await client.query<DeviceRow>(
      `INSERT INTO devices (name, type)
       VALUES ($1, $2)
       RETURNING id, name, type, created_at`,
      [input.name, input.type],
    );

    const device = toDevice(deviceRes.rows[0]);

    const keyRes = await client.query(
      `INSERT INTO api_keys (device_id, key_prefix, key_hash, scopes)
       VALUES ($1, $2, $3, $4)
       RETURNING id, key_prefix, scopes, created_at`,
      [device.id, keyPrefix, keyHash, scopes],
    );

    const apiKeyRow = keyRes.rows[0];

    await client.query("COMMIT");

    return {
      device, // modèle propre (createdAt)
      apiKey: {
        id: apiKeyRow.id,
        keyPrefix: apiKeyRow.key_prefix,
        scopes: apiKeyRow.scopes,
        createdAt: apiKeyRow.created_at,
        value: apiKey, // une seule fois
      },
    };
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
}

export interface PaginatedDevices {
  devices: Device[];
  total: number;
  limit: number;
  offset: number;
}

export async function listDevices(
  limit = 100,
  offset = 0,
): Promise<PaginatedDevices> {
  const safeLimit = Math.min(Math.max(limit, 1), 500);
  const safeOffset = Math.max(offset, 0);

  const [dataResult, countResult] = await Promise.all([
    pool.query<DeviceRow>(
      `SELECT id, name, type, created_at
       FROM devices
       ORDER BY created_at DESC
       LIMIT $1 OFFSET $2`,
      [safeLimit, safeOffset],
    ),
    pool.query<{ count: string }>(`SELECT COUNT(*) as count FROM devices`),
  ]);

  return {
    devices: dataResult.rows.map(toDevice),
    total: parseInt(countResult.rows[0].count, 10),
    limit: safeLimit,
    offset: safeOffset,
  };
}

export async function getDeviceById(id: string): Promise<Device | null> {
  const r = await pool.query<DeviceRow>(
    `SELECT id, name, type, created_at
     FROM devices
     WHERE id = $1`,
    [id],
  );

  return r.rowCount ? toDevice(r.rows[0]) : null;
}

export async function listRelays(): Promise<Device[]> {
  const result = await pool.query<DeviceRow>(
    `SELECT id, name, type, created_at
     FROM devices
     WHERE type = 'relay'
     ORDER BY created_at DESC`,
  );

  return result.rows.map(toDevice);
}

export async function listDashboards(): Promise<Device[]> {
  const result = await pool.query<DeviceRow>(
    `SELECT id, name, type, created_at
     FROM devices
     WHERE type = 'dashboard'
     ORDER BY created_at DESC`,
  );

  return result.rows.map(toDevice);
}

export async function listDrones(): Promise<Device[]> {
  const result = await pool.query<DeviceRow>(
    `SELECT id, name, type, created_at
     FROM devices
     WHERE type = 'drone'
     ORDER BY created_at DESC`,
  );

  return result.rows.map(toDevice);
}

export async function deleteDevice(id: string): Promise<boolean> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // Supprimer le device (les api_keys seront supprimées automatiquement via ON DELETE CASCADE)
    const result = await client.query(
      `DELETE FROM devices WHERE id = $1`,
      [id],
    );

    await client.query("COMMIT");

    const deleted = result.rowCount !== null && result.rowCount > 0;

    // Si le device a été supprimé, déconnecter tous ses sockets actifs
    if (deleted) {
      try {
        const io = getIO();
        const socketsInRoom = await io.in(roomDevice(id)).fetchSockets();
        
        logger.info("Déconnexion des sockets actifs pour le device supprimé", {
          deviceId: id,
          socketsCount: socketsInRoom.length,
        });

        for (const socket of socketsInRoom) {
          socket.disconnect(true); // true = fermeture forcée sans délai
        }
      } catch (ioError) {
        // Si Socket.IO n'est pas initialisé, on continue quand même
        logger.warn("Impossible de déconnecter les sockets (IO non initialisé)", {
          deviceId: id,
          error: ioError,
        });
      }
    }

    return deleted;
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
}
