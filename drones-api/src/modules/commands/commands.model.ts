export const COMMAND_LABELS = [
  "ARM",
  "ARM_FORCE",
  "DISARM",
  "GUIDED",
  "STABILIZE",
  "AUTO",
  "Mission Auto",
  "Loiter",
  "RTL",
  "Land",
  "Stop",
] as const;

export type CommandLabel = (typeof COMMAND_LABELS)[number];

export type SendCommandInput = {
  label: CommandLabel;
  droneId: string;
  requestedBy?: string;
};

export type SendCommandResult = {
  commandId: string;
  acceptedAt: number;
  relayId: string;
  droneId: string;
  label: CommandLabel;
};
