import { pool } from "../../db/pool";

type RelayDroneLinkRow = {
  id: string;
  relay_device_id: string;
  drone_device_id: string;
  active: boolean;
  created_at: string;
  revoked_at: string | null;
  revoked_reason: string | null;
};

export type RelayDroneLink = {
  id: string;
  relayDeviceId: string;
  droneDeviceId: string;
  active: boolean;
  createdAt: string;
  revokedAt: string | null;
  revokedReason: string | null;
};

function toRelayDroneLink(row: RelayDroneLinkRow): RelayDroneLink {
  return {
    id: row.id,
    relayDeviceId: row.relay_device_id,
    droneDeviceId: row.drone_device_id,
    active: row.active,
    createdAt: row.created_at,
    revokedAt: row.revoked_at,
    revokedReason: row.revoked_reason,
  };
}

export async function createRelayLink(relayId: string, droneId: string) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    // (optionnel mais recommandé) check types
    const [relayRes, droneRes] = await Promise.all([
      client.query<{ type: string }>(`SELECT type FROM devices WHERE id=$1`, [
        relayId,
      ]),
      client.query<{ type: string }>(`SELECT type FROM devices WHERE id=$1`, [
        droneId,
      ]),
    ]);

    if (relayRes.rowCount === 0) throw new Error("Relay not found");
    if (droneRes.rowCount === 0) throw new Error("Drone not found");

    if (relayRes.rows[0].type !== "relay") {
      throw new Error("relayDeviceId is not a relay");
    }
    if (droneRes.rows[0].type !== "drone") {
      throw new Error("droneDeviceId is not a drone");
    }

    // désactive un ancien lien actif pour ce drone
    await client.query(
      `
      UPDATE relay_drone_links
      SET active = false,
          revoked_at = now(),
          revoked_reason = 'Replaced by new link'
      WHERE drone_device_id = $1
        AND active = true
        AND revoked_at IS NULL
      `,
      [droneId]
    );

    // crée le nouveau lien
    const r = await client.query(
      `
      INSERT INTO relay_drone_links (relay_device_id, drone_device_id)
      VALUES ($1, $2)
      RETURNING id, relay_device_id, drone_device_id, active, created_at, revoked_at, revoked_reason
      `,
      [relayId, droneId]
    );

    await client.query("COMMIT");

    const row = r.rows[0] as RelayDroneLinkRow;
    return toRelayDroneLink(row);
  } catch (e) {
    await client.query("ROLLBACK");
    throw e;
  } finally {
    client.release();
  }
}

export async function getAllowedDroneIdsForRelay(relayId: string): Promise<string[]> {
  const r = await pool.query<{ drone_device_id: string }>(
    `SELECT drone_device_id
     FROM relay_drone_links
     WHERE relay_device_id = $1
       AND active = true
       AND revoked_at IS NULL`,
    [relayId],
  );
  return r.rows.map((x) => x.drone_device_id);
}

export async function getActiveRelayForDrone(droneId: string): Promise<string | null> {
  const r = await pool.query<{ relay_device_id: string }>(
    `SELECT relay_device_id
     FROM relay_drone_links
     WHERE drone_device_id = $1
       AND active = true
       AND revoked_at IS NULL
     LIMIT 1`,
    [droneId],
  );
  
  return r.rows[0]?.relay_device_id ?? null;
}

export async function listActiveRelayLinks(): Promise<RelayDroneLink[]> {
  const r = await pool.query<RelayDroneLinkRow>(
    `SELECT id, relay_device_id, drone_device_id, active, created_at, revoked_at, revoked_reason
     FROM relay_drone_links
     WHERE active = true
       AND revoked_at IS NULL
     ORDER BY created_at DESC`,
  );

  return r.rows.map(toRelayDroneLink);
}

export async function listActiveRelayLinksByRelay(
  relayId: string,
): Promise<RelayDroneLink[]> {
  const r = await pool.query<RelayDroneLinkRow>(
    `SELECT id, relay_device_id, drone_device_id, active, created_at, revoked_at, revoked_reason
     FROM relay_drone_links
     WHERE relay_device_id = $1
       AND active = true
       AND revoked_at IS NULL
     ORDER BY created_at DESC`,
    [relayId],
  );

  return r.rows.map(toRelayDroneLink);
}

export async function listActiveRelayLinksByDrone(
  droneId: string,
): Promise<RelayDroneLink[]> {
  const r = await pool.query<RelayDroneLinkRow>(
    `SELECT id, relay_device_id, drone_device_id, active, created_at, revoked_at, revoked_reason
     FROM relay_drone_links
     WHERE drone_device_id = $1
       AND active = true
       AND revoked_at IS NULL
     ORDER BY created_at DESC`,
    [droneId],
  );

  return r.rows.map(toRelayDroneLink);
}

export async function revokeRelayLink(
  linkId: string,
  reason?: string,
): Promise<boolean> {
  const r = await pool.query(
    `UPDATE relay_drone_links
     SET active = false,
         revoked_at = now(),
         revoked_reason = $2
     WHERE id = $1
       AND active = true
       AND revoked_at IS NULL`,
    [linkId, reason ?? "Manually delinked"],
  );

  return r.rowCount !== null && r.rowCount > 0;
}