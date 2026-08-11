export type LatestTelemetry = {
  droneId: string;
  ts: number;
  lat?: number;
  lon?: number;
  alt?: number;
  groundspeed?: number;
  mode?: string;
  sourceDeviceId?: string;
  receivedAt: string;
};

const latestTelemetryByDroneId = new Map<string, LatestTelemetry>();

export function upsertLatestTelemetry(
  payload: Omit<LatestTelemetry, "receivedAt">,
): LatestTelemetry {
  const entry: LatestTelemetry = {
    ...payload,
    receivedAt: new Date().toISOString(),
  };

  latestTelemetryByDroneId.set(payload.droneId, entry);
  return entry;
}

export function getLatestTelemetryByDroneId(
  droneId: string,
): LatestTelemetry | null {
  return latestTelemetryByDroneId.get(droneId) ?? null;
}
