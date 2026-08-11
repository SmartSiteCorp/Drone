import type { Request, Response } from "express";
import { z } from "zod";
import { getLatestTelemetryByDroneId } from "./telemetry.store";
import {
  getDroneTelemetryConfig,
  listRelayTelemetryConfigByRelay,
  upsertDroneTelemetryConfig,
} from "./telemetry.config.service";

const DroneIdParamSchema = z.object({
  droneId: z.string().uuid(),
});

const RelayIdQuerySchema = z.object({
  relayId: z.string().uuid(),
});

const UpsertTelemetryConfigSchema = z.object({
  mavlinkSysId: z.number().int().min(1).max(255),
});

export async function getLatestTelemetryHandler(req: Request, res: Response) {
  const parsed = DroneIdParamSchema.safeParse(req.params);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid drone id (expected uuid)" });
  }

  const telemetry = getLatestTelemetryByDroneId(parsed.data.droneId);
  if (!telemetry) {
    return res.status(404).json({
      error: "No telemetry yet for this drone",
      droneId: parsed.data.droneId,
    });
  }

  return res.json({ telemetry });
}

export async function upsertDroneTelemetryConfigHandler(
  req: Request,
  res: Response,
) {
  const parsedParams = DroneIdParamSchema.safeParse(req.params);
  if (!parsedParams.success) {
    return res.status(400).json({ error: "Invalid drone id (expected uuid)" });
  }

  const parsedBody = UpsertTelemetryConfigSchema.safeParse(req.body);
  if (!parsedBody.success) {
    return res.status(400).json({
      error: "Invalid payload",
      expected: { mavlinkSysId: "integer between 1 and 255" },
    });
  }

  try {
    const config = await upsertDroneTelemetryConfig(
      parsedParams.data.droneId,
      parsedBody.data.mavlinkSysId,
    );

    return res.json({ config });
  } catch (error) {
    const message = error instanceof Error ? error.message : "UNKNOWN";

    if (message === "DRONE_NOT_FOUND") {
      return res.status(404).json({ error: "Drone not found" });
    }

    if (message === "DEVICE_IS_NOT_DRONE") {
      return res.status(400).json({ error: "Device is not a drone" });
    }

    if (message === "MAVLINK_SYSID_ALREADY_USED") {
      return res.status(409).json({ error: "mavlinkSysId already assigned" });
    }

    throw error;
  }
}

export async function getDroneTelemetryConfigHandler(req: Request, res: Response) {
  const parsed = DroneIdParamSchema.safeParse(req.params);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid drone id (expected uuid)" });
  }

  const config = await getDroneTelemetryConfig(parsed.data.droneId);
  if (!config) {
    return res.status(404).json({
      error: "No telemetry config for this drone",
      droneId: parsed.data.droneId,
    });
  }

  return res.json({ config });
}

export async function listRelayTelemetryConfigHandler(req: Request, res: Response) {
  const parsed = RelayIdQuerySchema.safeParse(req.query);
  if (!parsed.success) {
    return res.status(400).json({ error: "relayId query param is required (uuid)" });
  }

  const items = await listRelayTelemetryConfigByRelay(parsed.data.relayId);
  return res.json({ relayId: parsed.data.relayId, items });
}
