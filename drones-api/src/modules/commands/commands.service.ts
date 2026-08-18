import { getIO } from "../../realtime/io";
import { roomDevice } from "../../realtime/rooms";
import { getActiveRelayForDrone } from "../relay-links/relay-links.service";
import type { SendCommandInput, SendCommandResult } from "./commands.model";

function buildCommandId() {
  return `cmd_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export async function sendCommandToDrone(
  input: SendCommandInput,
): Promise<SendCommandResult> {
  const relayId = await getActiveRelayForDrone(input.droneId);
  if (!relayId) {
    throw new Error("NO_ACTIVE_RELAY");
  }

  const commandId = buildCommandId();
  const acceptedAt = Date.now();

  const io = getIO();
  io.to(roomDevice(relayId)).emit("relay:command", {
    commandId,
    label: input.label,
    droneId: input.droneId,
    requestedBy: input.requestedBy ?? "api-rest",
  });

  return {
    commandId,
    acceptedAt,
    relayId,
    droneId: input.droneId,
    label: input.label,
  };
}
