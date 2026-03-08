import type { Request, Response } from "express";
import { z } from "zod";
import { CreateDeviceSchema } from "./devices.schemas";
import {
  createDevice,
  getDeviceById,
  listDevices,
  listRelays,
  listDashboards,
  listDrones,
  deleteDevice,
} from "./devices.service";

const DeviceIdParamSchema = z.object({
  id: z.string().uuid(),
});

export async function createDeviceHandler(req: Request, res: Response) {
  const input = CreateDeviceSchema.parse(req.body);
  const result = await createDevice(input);
  res.status(201).json(result);
}

export async function listDevicesHandler(req: Request, res: Response) {
  const parseQueryInt = (raw: unknown, defaultVal: number): number => {
    const str =
      typeof raw === "string" ? raw : Array.isArray(raw) ? raw[0] : undefined;
    const num = str ? Number(str) : defaultVal;
    return Number.isFinite(num) ? num : defaultVal;
  };

  const limit = parseQueryInt(req.query.limit, 100);
  const offset = parseQueryInt(req.query.offset, 0);

  const result = await listDevices(limit, offset);
  res.json(result);
}

export async function getDeviceByIdHandler(req: Request, res: Response) {
  const parsed = DeviceIdParamSchema.safeParse(req.params);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid device id (expected uuid)" });
  }

  const { id } = parsed.data;

  const device = await getDeviceById(id);
  if (!device) {
    return res.status(404).json({ error: "Device not found" });
  }

  res.json({ device });
}

export async function getAllRelays(req: Request, res: Response) {
  const relays = await listRelays();
  res.json({ relays });
}

export async function getAllDashboards(req: Request, res: Response) {
  const dashboards = await listDashboards();
  res.json({ dashboards });
}

export async function getAllDrones(req: Request, res: Response) {
  const drones = await listDrones();
  res.json({ drones });
}

export async function deleteDeviceHandler(req: Request, res: Response) {
  const parsed = DeviceIdParamSchema.safeParse(req.params);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid device id (expected uuid)" });
  }

  const { id } = parsed.data;

  const deleted = await deleteDevice(id);
  if (!deleted) {
    return res.status(404).json({ error: "Device not found" });
  }

  res.status(200).json({ message: "Device deleted successfully" });
}
