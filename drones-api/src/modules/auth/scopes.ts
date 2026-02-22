import type { DeviceType } from "../devices/devices.model";

export function defaultScopesForDevice(type: DeviceType): string[] {
  switch (type) {
    case "relay":
      return ["telemetry:write", "commands:read"];
    case "dashboard":
      return ["telemetry:read", "commands:write"];
    case "admin":
      return ["devices:manage", "keys:manage"];
    case "drone":
      return [];
  }
}
