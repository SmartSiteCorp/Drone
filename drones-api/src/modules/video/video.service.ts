import { randomBytes } from "crypto";

const streamTokens = new Map<string, { droneId: string; expiresAt: number }>();
const STREAM_TOKEN_TTL_MS = 5 * 60 * 1000;

export function createCameraStreamToken(droneId: string) {
  const token = randomBytes(32).toString("base64url");
  streamTokens.set(token, {
    droneId,
    expiresAt: Date.now() + STREAM_TOKEN_TTL_MS,
  });

  for (const [existingToken, value] of streamTokens) {
    if (value.expiresAt <= Date.now()) streamTokens.delete(existingToken);
  }

  return { token, expiresInSeconds: STREAM_TOKEN_TTL_MS / 1000 };
}

export function getCameraStreamDroneId(token: string): string | null {
  const value = streamTokens.get(token);
  if (!value || value.expiresAt <= Date.now()) {
    streamTokens.delete(token);
    return null;
  }

  return value.droneId;
}