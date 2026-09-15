const assert = require('node:assert/strict');
const { io } = require('socket.io-client');

const apiUrl = process.env.API_URL || 'http://localhost:7281';

async function apiRequest(path, method = 'GET', body) {
  const response = await fetch(`${apiUrl}${path}`, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error(`${method} ${path}: HTTP ${response.status} ${await response.text()}`);
  return response.json();
}

async function createDevice(type, name, createdIds) {
  const result = await apiRequest('/api/devices', 'POST', { type, name });
  if (result.device?.id) createdIds.push(result.device.id);
  assert.ok(result.device?.id && result.apiKey?.value, `Réponse de création invalide pour ${name}`);
  return result;
}

function waitFor(socket, event, predicate = () => true, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.off(event, handler);
      reject(new Error(`Timeout: ${event}`));
    }, timeoutMs);
    function handler(payload) {
      if (!predicate(payload)) return;
      clearTimeout(timer);
      socket.off(event, handler);
      resolve(payload);
    }
    socket.on(event, handler);
  });
}

function connect(key) {
  const socket = io(apiUrl, { auth: { apiKey: key }, transports: ['websocket'], autoConnect: false });
  const ready = Promise.race([
    waitFor(socket, 'connected'),
    waitFor(socket, 'connect_error').then(error => { throw error; }),
  ]);
  socket.connect();
  return { socket, ready };
}

async function sendCommand(socket, droneId) {
  const ack = await new Promise(resolve => socket.timeout(5000).emit('commande:send',
    { label: 'Stop', droneId }, (error, response) => resolve(error ? { ok: false, error: error.message } : response)));
  assert.equal(ack.ok, true, `Commande rejetée pour ${droneId}: ${ack.error}`);
  return ack;
}

async function main() {
  const createdIds = [];
  const sockets = [];
  try {
    await apiRequest('/health');
    const suffix = Date.now();
    const relayADevice = await createDevice('relay', `Test relay A ${suffix}`, createdIds);
    const relayBDevice = await createDevice('relay', `Test relay B ${suffix}`, createdIds);
    const droneADevice = await createDevice('drone', `Test drone A ${suffix}`, createdIds);
    const droneBDevice = await createDevice('drone', `Test drone B ${suffix}`, createdIds);
    const dashboardDevice = await createDevice('dashboard', `Test dashboard ${suffix}`, createdIds);
    const droneA = droneADevice.device.id;
    const droneB = droneBDevice.device.id;
    await apiRequest('/api/relay-links', 'POST', { relayDeviceId: relayADevice.device.id, droneDeviceId: droneA });
    await apiRequest('/api/relay-links', 'POST', { relayDeviceId: relayBDevice.device.id, droneDeviceId: droneB });

    const relayA = connect(relayADevice.apiKey.value);
    const relayB = connect(relayBDevice.apiKey.value);
    const dashboardA = connect(dashboardDevice.apiKey.value);
    const dashboardB = connect(dashboardDevice.apiKey.value);
    sockets.push(relayA.socket, relayB.socket, dashboardA.socket, dashboardB.socket);
    const [relayAInfo, relayBInfo, infoA, infoB] = await Promise.all([relayA.ready, relayB.ready, dashboardA.ready, dashboardB.ready]);
    assert.equal(relayAInfo.deviceType, 'relay');
    assert.equal(relayBInfo.deviceType, 'relay');
    assert.notEqual(relayAInfo.deviceId, relayBInfo.deviceId);
    assert.equal(infoA.deviceType, 'dashboard');
    assert.equal(infoB.deviceType, 'dashboard');
    assert.deepEqual(relayAInfo.allowedDroneIds, [droneA], 'Le relais A doit être lié uniquement au drone A');
    assert.deepEqual(relayBInfo.allowedDroneIds, [droneB], 'Le relais B doit être lié uniquement au drone B');

    const subscribed = Promise.all([
      waitFor(dashboardA.socket, 'telemetry:subscribed', p => p.droneId === droneA),
      waitFor(dashboardB.socket, 'telemetry:subscribed', p => p.droneId === droneB),
    ]);
    dashboardA.socket.emit('telemetry:subscribe', { droneId: droneA });
    dashboardB.socket.emit('telemetry:subscribe', { droneId: droneB });
    await subscribed;

    const receivedA = [];
    const receivedB = [];
    const commandsA = [];
    const commandsB = [];
    dashboardA.socket.on('telemetry:update', p => receivedA.push(p));
    dashboardB.socket.on('telemetry:update', p => receivedB.push(p));
    relayA.socket.on('relay:command', p => commandsA.push(p));
    relayB.socket.on('relay:command', p => commandsB.push(p));
    for (const [id, altitude] of [[droneA, 101], [droneB, 202]]) {
      const ts = Date.now();
      const relay = id === droneA ? relayA.socket : relayB.socket;
      const ackPromise = waitFor(relay, 'telemetry:push:ack', p => p.droneId === id && p.ts === ts);
      const dashboard = id === droneA ? dashboardA.socket : dashboardB.socket;
      const updatePromise = waitFor(dashboard, 'telemetry:update', p => p.droneId === id && p.ts === ts);
      relay.emit('telemetry:push', { droneId: id, ts, alt: altitude });
      await Promise.all([ackPromise, updatePromise]);
    }
    await new Promise(resolve => setTimeout(resolve, 200));
    assert.deepEqual(receivedA.map(p => [p.droneId, p.alt]), [[droneA, 101]]);
    assert.deepEqual(receivedB.map(p => [p.droneId, p.alt]), [[droneB, 202]]);

    const rejection = waitFor(relayA.socket, 'app:error', p => p.event === 'telemetry:push' && p.droneId === droneB);
    relayA.socket.emit('telemetry:push', { droneId: droneB, ts: Date.now() });
    assert.match((await rejection).message, /non autorisé/);

    for (const id of [droneA, droneB]) {
      const relay = id === droneA ? relayA.socket : relayB.socket;
      const commandPromise = waitFor(relay, 'relay:command', p => p.droneId === id);
      await sendCommand(dashboardA.socket, id);
      const command = await commandPromise;
      assert.equal(command.label, 'Stop');
      await new Promise(resolve => setTimeout(resolve, 750));
    }
    assert.deepEqual(commandsA.map(p => p.droneId), [droneA]);
    assert.deepEqual(commandsB.map(p => p.droneId), [droneB]);
    console.log('OK : télémétrie et commandes isolées entre deux couples relais-drone.');
  } finally {
    for (const socket of sockets) socket.disconnect();
    for (const id of createdIds.reverse()) {
      try {
        await apiRequest(`/api/devices/${id}`, 'DELETE');
      } catch (error) {
        console.error(`Nettoyage impossible pour le device ${id}: ${error.message}`);
        process.exitCode = 1;
      }
    }
  }
}

main().catch(error => {
  console.error('ÉCHEC multi-drones:', error.message);
  process.exitCode = 1;
});
