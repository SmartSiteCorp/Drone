import type { Device } from "./devices.model";

export type DeviceRow = {
  id: string;
  name: string;
  type: string;
  created_at: string;
};

export function toDevice(row: DeviceRow): Device {
  return {
    id: row.id,
    name: row.name,
    type: row.type as Device["type"],
    createdAt: row.created_at,
  };
}
