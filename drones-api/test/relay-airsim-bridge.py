import os
import time
import json
import threading
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

import socketio
from pymavlink import mavutil


API_URL = os.getenv("API_URL", "http://localhost:7281")
RELAY_API_KEY = os.getenv("RELAY_API_KEY")
DRONE_ID = os.getenv("DRONE_ID")
DRONE_ID_BY_SYSID_RAW = os.getenv("DRONE_ID_BY_SYSID", "")
AUTO_CONFIG_FROM_API = os.getenv("AUTO_CONFIG_FROM_API", "1").lower() in ("1", "true", "yes")
CONFIG_REFRESH_SEC = float(os.getenv("CONFIG_REFRESH_SEC", "5"))
MAVLINK_ENDPOINT = os.getenv("MAVLINK_ENDPOINT", "udpin:0.0.0.0:14550")
PUSH_HZ = float(os.getenv("PUSH_HZ", "2"))


if not RELAY_API_KEY:
    raise SystemExit("Missing RELAY_API_KEY environment variable")

drone_id_by_sysid: Dict[str, str] = {}
if DRONE_ID_BY_SYSID_RAW.strip():
    try:
        parsed = json.loads(DRONE_ID_BY_SYSID_RAW)
        if not isinstance(parsed, dict):
            raise ValueError("must be a JSON object")

        # Normalize keys/values as strings.
        for k, v in parsed.items():
            drone_id_by_sysid[str(k)] = str(v)
    except Exception as exc:
        raise SystemExit(
            "Invalid DRONE_ID_BY_SYSID. Expected JSON object like {'1':'uuid-1','2':'uuid-2'}"
        ) from exc

if not DRONE_ID and not drone_id_by_sysid and not AUTO_CONFIG_FROM_API:
    raise SystemExit(
        "Missing routing config: set DRONE_ID, DRONE_ID_BY_SYSID, or AUTO_CONFIG_FROM_API=1"
    )

if PUSH_HZ <= 0:
    raise SystemExit("PUSH_HZ must be > 0")


sio = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
runtime_drone_id_by_sysid: Dict[str, str] = {}
runtime_map_lock = threading.Lock()
relay_device_id: Optional[str] = None
mav_conn: Any = None
target_by_drone: Dict[str, Dict[str, int]] = {}


def wait_command_ack(command_id: int, timeout_sec: float = 1.5) -> None:
    if mav_conn is None:
        return

    start = time.time()
    while time.time() - start < timeout_sec:
        msg = mav_conn.recv_match(type="COMMAND_ACK", blocking=False)
        if msg is None:
            time.sleep(0.05)
            continue

        if int(getattr(msg, "command", -1)) != int(command_id):
            continue

        result = int(getattr(msg, "result", -1))
        print(f"[bridge] COMMAND_ACK command={command_id} result={result}")
        return

    print(f"[bridge] COMMAND_ACK timeout command={command_id}")


def get_target_for_drone(drone_id: str) -> Dict[str, int]:
    target = target_by_drone.get(drone_id)
    if target:
        return target

    # Fallback values commonly used by ArduPilot autopilot component.
    return {"sysid": 1, "compid": 1}


def send_mode_change(mode_name: str, target_sysid: int) -> None:
    if mav_conn is None:
        print("[bridge] MAVLink not ready, mode change ignored")
        return

    mapping = mav_conn.mode_mapping() or {}
    mode_id = None

    for key, value in mapping.items():
        if str(key).upper() == mode_name.upper():
            mode_id = int(value)
            break

    if mode_id is None:
        print(f"[bridge] Mode '{mode_name}' unsupported by autopilot mapping: {mapping}")
        return

    mav_conn.mav.set_mode_send(
        target_sysid,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )
    print(f"[bridge] Sent SET_MODE {mode_name} (custom_mode={mode_id})")


@sio.event
def connect() -> None:
    print("[bridge] Connected to API")


@sio.event
def disconnect() -> None:
    print("[bridge] Disconnected from API")


@sio.on("connected")
def on_connected(payload: Dict[str, Any]) -> None:
    global relay_device_id
    relay_device_id = payload.get("deviceId")
    print("[bridge] Server auth context:", payload)


@sio.on("relay:command")
def on_relay_command(payload: Dict[str, Any]) -> None:
    print("[bridge] relay:command received:", payload)

    global mav_conn
    if mav_conn is None:
        print("[bridge] MAVLink not ready, command ignored")
        return

    label = payload.get("label")
    drone_id = payload.get("droneId")
    if not isinstance(drone_id, str):
        print("[bridge] Missing droneId in relay:command payload")
        return

    target = get_target_for_drone(drone_id)
    target_sysid = int(target["sysid"])
    target_compid = int(target["compid"])
    print(
        f"[bridge] Dispatch command label={label} to sysid={target_sysid} compid={target_compid}"
    )

    # ArduPilot convention: param2=21196 forces arm/disarm checks bypass.
    if label == "ARM":
        mav_conn.mav.command_long_send(
            target_sysid,
            target_compid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        print("[bridge] Sent MAV_CMD_COMPONENT_ARM_DISARM (ARM)")
        wait_command_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
        return

    if label == "ARM_FORCE":
        mav_conn.mav.command_long_send(
            target_sysid,
            target_compid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1,
            21196,
            0,
            0,
            0,
            0,
            0,
        )
        print("[bridge] Sent MAV_CMD_COMPONENT_ARM_DISARM (ARM_FORCE)")
        wait_command_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
        return

    if label == "DISARM":
        mav_conn.mav.command_long_send(
            target_sysid,
            target_compid,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        print("[bridge] Sent MAV_CMD_COMPONENT_ARM_DISARM (DISARM)")
        wait_command_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM)
        return

    if label == "GUIDED":
        send_mode_change("GUIDED", target_sysid)
        return

    if label == "STABILIZE":
        send_mode_change("STABILIZE", target_sysid)
        return

    if label in ("AUTO", "Mission Auto"):
        send_mode_change("AUTO", target_sysid)
        return

    if label == "Loiter":
        send_mode_change("LOITER", target_sysid)
        return

    if label == "RTL":
        send_mode_change("RTL", target_sysid)
        return

    if label == "Land":
        send_mode_change("LAND", target_sysid)
        return

    print(f"[bridge] Command label '{label}' received (no MAVLink mapping yet)")


def try_get_mode(msg: Any) -> Optional[str]:
    try:
        return mavutil.mode_string_v10(msg)
    except Exception:
        return None


def resolve_drone_id(msg: Any) -> Optional[str]:
    if drone_id_by_sysid:
        try:
            sysid = str(msg.get_srcSystem())
        except Exception:
            return None
        return drone_id_by_sysid.get(sysid)

    if AUTO_CONFIG_FROM_API:
        try:
            sysid = str(msg.get_srcSystem())
        except Exception:
            return None

        with runtime_map_lock:
            return runtime_drone_id_by_sysid.get(sysid)

    return DRONE_ID


def fetch_runtime_mapping_from_api() -> None:
    if not relay_device_id:
        return

    query = urllib.parse.urlencode({"relayId": relay_device_id})
    url = f"{API_URL.rstrip('/')}/api/telemetry/config/by-relay?{query}"

    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))

    items = payload.get("items", [])
    new_mapping: Dict[str, str] = {}

    for item in items:
        sysid = item.get("mavlinkSysId")
        drone_id = item.get("droneId")
        if isinstance(sysid, int) and isinstance(drone_id, str):
            new_mapping[str(sysid)] = drone_id

    with runtime_map_lock:
        runtime_drone_id_by_sysid.clear()
        runtime_drone_id_by_sysid.update(new_mapping)

    if new_mapping:
        print("[bridge] Runtime mapping updated from API:", new_mapping)


def config_poller_loop() -> None:
    while True:
        try:
            if AUTO_CONFIG_FROM_API:
                fetch_runtime_mapping_from_api()
        except Exception as exc:
            print("[bridge] Failed to refresh runtime mapping:", exc)

        time.sleep(CONFIG_REFRESH_SEC)


def main() -> None:
    global mav_conn
    print("[bridge] API_URL:", API_URL)
    print("[bridge] DRONE_ID:", DRONE_ID)
    if drone_id_by_sysid:
        print("[bridge] DRONE_ID_BY_SYSID:", drone_id_by_sysid)
    print("[bridge] AUTO_CONFIG_FROM_API:", AUTO_CONFIG_FROM_API)
    print("[bridge] CONFIG_REFRESH_SEC:", CONFIG_REFRESH_SEC)
    print("[bridge] MAVLINK_ENDPOINT:", MAVLINK_ENDPOINT)
    print("[bridge] PUSH_HZ:", PUSH_HZ)

    sio.connect(
        API_URL,
        auth={"apiKey": RELAY_API_KEY},
        headers={"x-api-key": RELAY_API_KEY},
        transports=["websocket"],
        wait_timeout=10,
    )

    if AUTO_CONFIG_FROM_API:
        t = threading.Thread(target=config_poller_loop, daemon=True)
        t.start()

    mav = mavutil.mavlink_connection(MAVLINK_ENDPOINT)
    mav_conn = mav
    print("[bridge] Waiting MAVLink heartbeat...")
    mav.wait_heartbeat(timeout=60)
    print("[bridge] MAVLink heartbeat received")

    state_by_drone: Dict[str, Dict[str, Any]] = {}

    min_interval = 1.0 / PUSH_HZ
    last_push = 0.0

    while True:
        msg = mav.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue

        drone_id = resolve_drone_id(msg)
        if not drone_id:
            continue

        if drone_id not in state_by_drone:
            state_by_drone[drone_id] = {
                "lat": None,
                "lon": None,
                "alt": None,
                "groundspeed": None,
                "mode": None,
            }

        try:
            target_by_drone[drone_id] = {
                "sysid": int(msg.get_srcSystem()),
                "compid": int(msg.get_srcComponent()),
            }
        except Exception:
            pass

        state = state_by_drone[drone_id]
        mtype = msg.get_type()

        if mtype == "GLOBAL_POSITION_INT":
            # lat/lon in 1e7, relative_alt in mm
            state["lat"] = float(msg.lat) / 1e7
            state["lon"] = float(msg.lon) / 1e7
            state["alt"] = float(msg.relative_alt) / 1000.0

        elif mtype == "VFR_HUD":
            state["groundspeed"] = float(msg.groundspeed)
            if state["alt"] is None:
                state["alt"] = float(msg.alt)

        elif mtype == "HEARTBEAT":
            mode = try_get_mode(msg)
            if mode:
                state["mode"] = mode

        now = time.time()
        if now - last_push < min_interval:
            continue

        payload = {
            "droneId": drone_id,
            "ts": int(time.time() * 1000),
        }

        # Publish partial telemetry even without GPS fix.
        if state["lat"] is not None:
            payload["lat"] = state["lat"]
        if state["lon"] is not None:
            payload["lon"] = state["lon"]
        if state["alt"] is not None:
            payload["alt"] = state["alt"]
        if state["groundspeed"] is not None:
            payload["groundspeed"] = state["groundspeed"]
        if state["mode"] is not None:
            payload["mode"] = state["mode"]

        sio.emit("telemetry:push", payload)
        print("[bridge] telemetry:push", payload)
        last_push = now


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[bridge] Stopped by user")
    finally:
        try:
            sio.disconnect()
        except Exception:
            pass
