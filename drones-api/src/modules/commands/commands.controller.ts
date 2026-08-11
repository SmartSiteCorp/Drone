import type { Request, Response } from "express";
import { SendCommandSchema } from "./commands.schemas";
import { sendCommandToDrone } from "./commands.service";

export async function sendCommandHandler(req: Request, res: Response) {
  const parsed = SendCommandSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({
      error: "Invalid payload",
      expected: {
        label: "ARM|ARM_FORCE|DISARM|GUIDED|STABILIZE|AUTO|Mission Auto|Loiter|RTL|Land|Stop",
        droneId: "uuid",
      },
    });
  }

  try {
    const result = await sendCommandToDrone({
      ...parsed.data,
      requestedBy: "api-rest",
    });

    return res.status(202).json({ ok: true, ...result });
  } catch (error) {
    const message = error instanceof Error ? error.message : "UNKNOWN";

    if (message === "NO_ACTIVE_RELAY") {
      return res
        .status(409)
        .json({ error: "Aucun relay actif pour ce drone" });
    }

    throw error;
  }
}
