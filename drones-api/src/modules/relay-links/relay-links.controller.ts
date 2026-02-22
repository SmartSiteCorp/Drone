import type { Request, Response } from "express";
import { z } from "zod";
import { createRelayLink } from "./relay-links.service";

const CreateRelayLinkSchema = z.object({
  relayDeviceId: z.string().uuid(),
  droneDeviceId: z.string().uuid(),
});

export async function createRelayLinkHandler(req: Request, res: Response) {
  const input = CreateRelayLinkSchema.parse(req.body);

  const link = await createRelayLink(input.relayDeviceId, input.droneDeviceId);

  res.status(201).json({ link });
}