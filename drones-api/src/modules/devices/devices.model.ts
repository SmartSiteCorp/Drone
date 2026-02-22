export type DeviceType = "relay" | "drone" | "dashboard" | "admin";

export type Device = {
  id: string;
  name: string;
  type: DeviceType;
  createdAt: string; // ISO
};
