import { z } from "zod";
import { COMMAND_LABELS } from "./commands.model";

export const SendCommandSchema = z.object({
  label: z.enum(COMMAND_LABELS),
  droneId: z.string().uuid(),
});

export type SendCommandBody = z.infer<typeof SendCommandSchema>;
