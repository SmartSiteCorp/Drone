const API_URL = (process.env.API_URL || "http://localhost:7281").replace(/\/$/, "");
const API_KEY = process.env.DASHBOARD_API_KEY;
const DRONE_ID = process.env.DRONE_ID;
const action = process.argv[2] || "start";

if (!API_KEY || !DRONE_ID) {
  console.error("Set DASHBOARD_API_KEY and DRONE_ID before running this script.");
  process.exit(1);
}

if (action !== "start" && action !== "stop") {
  console.error("Usage: node test/test-camera-stream.js [start|stop]");
  process.exit(1);
}

async function post(path) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "x-api-key": API_KEY },
  });
  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${JSON.stringify(body)}`);
  }

  return body;
}

async function main() {
  const encodedDroneId = encodeURIComponent(DRONE_ID);
  const result = await post(`/api/video/${encodedDroneId}/${action}`);
  console.log(`Camera ${action} request accepted:`, result);

  if (action === "start") {
    const access = await post(`/api/video/${encodedDroneId}/access-token`);
    console.log("Open the MediaMTX WebRTC player:");
    console.log(access.playerUrl);
    console.log("If the stream is not ready yet, wait a few seconds and refresh the player.");
    console.log("For the browser authentication prompt, enter username 'viewer' and this password:");
    console.log(access.token);
    console.log("HLS player fallback:", access.hlsPlayerUrl);
    console.log(`The access token expires in ${access.expiresInSeconds} seconds.`);
  }
}

main().catch((error) => {
  console.error(`Camera stream request failed: ${error.message}`);
  process.exitCode = 1;
});
