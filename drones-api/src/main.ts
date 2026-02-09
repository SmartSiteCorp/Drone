import "dotenv/config";
import http from "http";
import { createApp } from "./app";

const PORT = Number(process.env.PORT ?? 7281);

const app = createApp();
const server = http.createServer(app);

server.listen(PORT, () => {
  console.log(`API running on http://localhost:${PORT}`);
});