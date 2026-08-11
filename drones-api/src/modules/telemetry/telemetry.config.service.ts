import { pool } from "../../db/pool";

export type DroneTelemetryConfig = {
  droneId: string;
  mavlinkSysId: number;
  updatedAt: string;
};

export type RelayTelemetryConfigItem = {
  droneId: string;
  mavlinkSysId: number | null;
};

let ensureConfigTablePromise: Promise<void> | null = null;

async function ensureTelemetryConfigTable() {
  if (!ensureConfigTablePromise) {
    ensureConfigTablePromise = (async () => {
      await pool.query(`
        CREATE TABLE IF NOT EXISTS drone_telemetry_configs (
          drone_device_id uuid PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
          mavlink_sysid integer NOT NULL CHECK (mavlink_sysid >= 1 AND mavlink_sysid <= 255),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
      `);

      await pool.query(`
        CREATE UNIQUE INDEX IF NOT EXISTS drone_telemetry_configs_mavlink_sysid_uidx
        ON drone_telemetry_configs(mavlink_sysid)
      `);
    })();
  }

  await ensureConfigTablePromise;
}

async function assertDroneDevice(droneId: string) {
  const r = await pool.query<{ type: string }>(
    `SELECT type FROM devices WHERE id = $1`,
    [droneId],
  );

  if (r.rowCount === 0) {
    throw new Error("DRONE_NOT_FOUND");
  }

  if (r.rows[0].type !== "drone") {
    throw new Error("DEVICE_IS_NOT_DRONE");
  }
}

export async function upsertDroneTelemetryConfig(
  droneId: string,
  mavlinkSysId: number,
): Promise<DroneTelemetryConfig> {
  await ensureTelemetryConfigTable();
  await assertDroneDevice(droneId);

  try {
    const r = await pool.query<{
      drone_device_id: string;
      mavlink_sysid: number;
      updated_at: string;
    }>(
      `INSERT INTO drone_telemetry_configs (drone_device_id, mavlink_sysid)
       VALUES ($1, $2)
       ON CONFLICT (drone_device_id)
       DO UPDATE SET mavlink_sysid = EXCLUDED.mavlink_sysid, updated_at = now()
       RETURNING drone_device_id, mavlink_sysid, updated_at`,
      [droneId, mavlinkSysId],
    );

    return {
      droneId: r.rows[0].drone_device_id,
      mavlinkSysId: r.rows[0].mavlink_sysid,
      updatedAt: r.rows[0].updated_at,
    };
  } catch (error: any) {
    if (error?.code === "23505") {
      throw new Error("MAVLINK_SYSID_ALREADY_USED");
    }

    throw error;
  }
}

export async function getDroneTelemetryConfig(
  droneId: string,
): Promise<DroneTelemetryConfig | null> {
  await ensureTelemetryConfigTable();

  const r = await pool.query<{
    drone_device_id: string;
    mavlink_sysid: number;
    updated_at: string;
  }>(
    `SELECT drone_device_id, mavlink_sysid, updated_at
     FROM drone_telemetry_configs
     WHERE drone_device_id = $1`,
    [droneId],
  );

  if (!r.rowCount) {
    return null;
  }

  return {
    droneId: r.rows[0].drone_device_id,
    mavlinkSysId: r.rows[0].mavlink_sysid,
    updatedAt: r.rows[0].updated_at,
  };
}

export async function listRelayTelemetryConfigByRelay(
  relayId: string,
): Promise<RelayTelemetryConfigItem[]> {
  await ensureTelemetryConfigTable();

  const r = await pool.query<{
    drone_device_id: string;
    mavlink_sysid: number | null;
  }>(
    `SELECT l.drone_device_id, c.mavlink_sysid
     FROM relay_drone_links l
     LEFT JOIN drone_telemetry_configs c ON c.drone_device_id = l.drone_device_id
     WHERE l.relay_device_id = $1
       AND l.active = true
       AND l.revoked_at IS NULL
     ORDER BY l.created_at DESC`,
    [relayId],
  );

  return r.rows.map((row) => ({
    droneId: row.drone_device_id,
    mavlinkSysId: row.mavlink_sysid,
  }));
}
