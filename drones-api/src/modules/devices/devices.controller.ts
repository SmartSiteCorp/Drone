import type { Request, Response } from "express";
import { CreateDeviceSchema } from "./devices.schemas";
import { createDevice } from "./devices.service";

export async function createDeviceHandler(req: Request, res: Response) {
  const input = CreateDeviceSchema.parse(req.body);
  const result = await createDevice(input);
  res.status(201).json(result);
}
