import { z } from "zod";

export const CreateDeviceSchema = z.object({
  name: z.string().min(1).max(100),
  type: z.enum(["relay", "dashboard", "admin"]),
  // optionnel : si absent, on mettra des scopes par défaut selon type
  scopes: z.array(z.string().min(1)).optional(),
});

export type CreateDeviceInput = z.infer<typeof CreateDeviceSchema>;
