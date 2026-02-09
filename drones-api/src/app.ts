import express from "express";
import cors from "cors";
import helmet from "helmet";
import { errorHandler } from "./http/middlewares/errorHandler";
import { router } from "./http/router";

export function createApp() {
  const app = express();

  app.use(helmet());
  app.use(cors());
  app.use(express.json());

  app.use(router);

  app.use(errorHandler);

  return app;
}
