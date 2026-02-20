import type { Request, Response, NextFunction } from "express";
import { logger } from "../../core/logger";

export function errorHandler(
  err: unknown,
  req: Request,
  res: Response,
  _next: NextFunction
) {
  const error = err instanceof Error ? err : new Error("Unknown error");

  logger.error("HTTP_ERROR", {
    message: error.message,
    stack: error.stack,
    method: req.method,
    url: req.originalUrl,
    body: req.body,
  });

  res.status(500).json({
    error: "Internal server error",
  });
}