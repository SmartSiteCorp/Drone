import "dotenv/config";
import http from "http";
import { createApp } from "./app";
import { createIO } from "./realtime/io";
import { registerSocketHandlers } from "./realtime";
import { useApiKeyAuth } from "./realtime/authApiKey";

const PORT = Number(process.env.PORT ?? 7281);

const app = createApp();
const server = http.createServer(app);


const io = createIO(server);
useApiKeyAuth(io);
registerSocketHandlers(io);

server.listen(PORT, () => {
  console.log(`API running on http://localhost:${PORT}`);
});