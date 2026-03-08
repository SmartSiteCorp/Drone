import type { Request, Response } from "express";
import { z } from "zod";
import {
  createRelayLink,
  listActiveRelayLinks,
  listActiveRelayLinksByDrone,
  listActiveRelayLinksByRelay,
  revokeRelayLink,
} from "./relay-links.service";

const CreateRelayLinkSchema = z.object({
  relayDeviceId: z.string().uuid(),
  droneDeviceId: z.string().uuid(),
});

const RelayIdQuerySchema = z.object({
  relayId: z.string().uuid(),
});

const DroneIdQuerySchema = z.object({
  droneId: z.string().uuid(),
});

const LinkIdParamSchema = z.object({
  id: z.string().uuid(),
});

export async function createRelayLinkHandler(req: Request, res: Response) {
  const input = CreateRelayLinkSchema.parse(req.body);

  const link = await createRelayLink(input.relayDeviceId, input.droneDeviceId);

  res.status(201).json({ link });
}

export async function listRelayLinksHandler(_req: Request, res: Response) {
  const links = await listActiveRelayLinks();
  res.json({ links });
}

export async function listRelayLinksByRelayHandler(req: Request, res: Response) {
  const parsed = RelayIdQuerySchema.safeParse(req.query);
  if (!parsed.success) {
    return res.status(400).json({ error: "relayId query param is required (uuid)" });
  }

  const links = await listActiveRelayLinksByRelay(parsed.data.relayId);
  return res.json({ relayId: parsed.data.relayId, links });
}

export async function listRelayLinksByDroneHandler(req: Request, res: Response) {
  const parsed = DroneIdQuerySchema.safeParse(req.query);
  if (!parsed.success) {
    return res.status(400).json({ error: "droneId query param is required (uuid)" });
  }

  const links = await listActiveRelayLinksByDrone(parsed.data.droneId);
  return res.json({ droneId: parsed.data.droneId, links });
}

export async function revokeRelayLinkHandler(req: Request, res: Response) {
  const parsed = LinkIdParamSchema.safeParse(req.params);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid link id (expected uuid)" });
  }

  const revoked = await revokeRelayLink(parsed.data.id);
  if (!revoked) {
    return res.status(404).json({ error: "Link not found or already revoked" });
  }

  return res.json({ message: "Link revoked successfully" });
}