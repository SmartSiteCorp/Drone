export type DeviceType = "relay" | "dashboard" | "admin";

export type Device = {
  id: string;
  name: string;
  type: DeviceType;
  createdAt: string; // ISO
};
