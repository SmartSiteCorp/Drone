import os
import time
import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import socketio
from pymavlink import mavutil

try:
    from dotenv import load_dotenv
except Exception as exc:
    raise SystemExit(
        "Missing dependency 'python-dotenv'. Install with: pip install python-dotenv"
    ) from exc


# Load project .env automatically so manual export is optional.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(override=False)


API_URL = os.getenv("API_URL", "http://localhost:7281")
RELAY_API_KEY = os.getenv("RELAY_API_KEY")
DRONE_ID = os.getenv("DRONE_ID")
DRONE_ID_BY_SYSID_RAW = os.getenv("DRONE_ID_BY_SYSID", "")
AUTO_CONFIG_FROM_API = os.getenv("AUTO_CONFIG_FROM_API", "1").lower() in (
    "1",
    "true",
    "yes",
)
CONFIG_REFRESH_SEC = float(os.getenv("CONFIG_REFRESH_SEC", "5"))
MAVLINK_ENDPOINT = os.getenv(
    "MAVLINK_ENDPOINT",
    "udpin:0.0.0.0:14550",
)
PUSH_HZ = float(os.getenv("PUSH_HZ", "2"))


if not RELAY_API_KEY:
    raise SystemExit(
        "Missing RELAY_API_KEY environment variable"
    )


drone_id_by_sysid: Dict[str, str] = {}

if DRONE_ID_BY_SYSID_RAW.strip():
    try:
        parsed = json.loads(DRONE_ID_BY_SYSID_RAW)

        if not isinstance(parsed, dict):
            raise ValueError("must be a JSON object")

        for k, v in parsed.items():
            drone_id_by_sysid[str(k)] = str(v)

    except Exception as exc:
        raise SystemExit(
            "Invalid DRONE_ID_BY_SYSID. "
            "Expected JSON object like "
            "{'1':'uuid-1','2':'uuid-2'}"
        ) from exc


if (
    not DRONE_ID
    and not drone_id_by_sysid
    and not AUTO_CONFIG_FROM_API
):
    raise SystemExit(
        "Missing routing config: set DRONE_ID, "
        "DRONE_ID_BY_SYSID, or AUTO_CONFIG_FROM_API=1"
    )


if PUSH_HZ <= 0:
    raise SystemExit("PUSH_HZ must be > 0")


sio = socketio.Client(
    reconnection=True,
    logger=False,
    engineio_logger=False,
)

runtime_drone_id_by_sysid: Dict[str, str] = {}
runtime_map_lock = threading.Lock()

relay_device_id: Optional[str] = None
mav_conn: Any = None

target_by_drone: Dict[str, Dict[str, int]] = {}

# Empêche deux uploads de mission en même temps
mission_lock = threading.Lock()

# Sérialise les lectures MAVLink pour éviter que deux threads
# consomment les mêmes messages (ACK, HEARTBEAT, mission requests).
mav_io_lock = threading.Lock()

# Pendant un upload, la boucle télémétrie ne doit pas
# consommer les MISSION_REQUEST_INT / MISSION_ACK.
mission_in_progress = threading.Event()


# ============================================================
# MAVLINK HELPERS
# ============================================================

def wait_command_ack(
    command_id: int,
    timeout_sec: float = 1.5,
) -> None:
    if mav_conn is None:
        return

    start = time.time()

    while time.time() - start < timeout_sec:
        # Ne pas voler les messages pendant un upload mission
        if mission_in_progress.is_set():
            time.sleep(0.05)
            continue

        with mav_io_lock:
            msg = mav_conn.recv_match(
                type="COMMAND_ACK",
                blocking=False,
            )

        if msg is None:
            time.sleep(0.05)
            continue

        if int(
            getattr(msg, "command", -1)
        ) != int(command_id):
            continue

        result = int(
            getattr(msg, "result", -1)
        )

        print(
            f"[bridge] COMMAND_ACK "
            f"command={command_id} result={result}"
        )

        return

    print(
        f"[bridge] COMMAND_ACK timeout "
        f"command={command_id}"
    )


def get_target_for_drone(
    drone_id: str,
) -> Dict[str, int]:
    target = target_by_drone.get(drone_id)

    if target:
        return target

    # Fallback ArduPilot classique
    return {
        "sysid": 1,
        "compid": 1,
    }


def send_mode_change(
    mode_name: str,
    target_sysid: int,
) -> bool:
    if mav_conn is None:
        print(
            "[bridge] MAVLink not ready, "
            "mode change ignored"
        )
        return False

    mapping = mav_conn.mode_mapping() or {}

    mode_id = None

    for key, value in mapping.items():
        if str(key).upper() == mode_name.upper():
            mode_id = int(value)
            break

    if mode_id is None:
        print(
            f"[bridge] Mode '{mode_name}' unsupported "
            f"by autopilot mapping: {mapping}"
        )
        return False

    mav_conn.mav.set_mode_send(
        target_sysid,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )

    print(
        f"[bridge] Sent SET_MODE {mode_name} "
        f"(custom_mode={mode_id})"
    )

    if wait_for_mode(target_sysid, mode_name, timeout_sec=2.5):
        return True

    # Fallback explicite: certains autopilots répondent mieux à DO_SET_MODE.
    mav_conn.mav.command_long_send(
        target_sysid,
        1,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
        0,
        0,
        0,
        0,
        0,
    )

    print(
        f"[bridge] Sent MAV_CMD_DO_SET_MODE {mode_name} "
        f"(custom_mode={mode_id})"
    )

    wait_command_ack(mavutil.mavlink.MAV_CMD_DO_SET_MODE)
    return wait_for_mode(target_sysid, mode_name, timeout_sec=2.5)


def wait_for_mode(
    target_sysid: int,
    expected_mode: str,
    timeout_sec: float = 2.5,
) -> bool:
    expected = expected_mode.upper()
    deadline = time.time() + timeout_sec

    while time.time() < deadline:
        if mav_conn is None:
            return False

        with mav_io_lock:
            msg = mav_conn.recv_match(
                type="HEARTBEAT",
                blocking=False,
            )

        if msg is None:
            time.sleep(0.05)
            continue

        try:
            if int(msg.get_srcSystem()) != int(target_sysid):
                continue
        except Exception:
            continue

        mode = try_get_mode(msg)
        if mode and mode.upper() == expected:
            print(f"[bridge] Mode confirmé: {mode}")
            return True

    print(f"[bridge] Mode '{expected_mode}' non confirmé")
    return False


def start_mission(
    target_sysid: int,
    target_compid: int,
) -> None:
    if mav_conn is None:
        print(
            "[bridge] MAVLink not ready, "
            "mission start ignored"
        )
        return

    # Revenir au premier item pour éviter le cas "AUTO mais mission terminée".
    try:
        mav_conn.mav.mission_set_current_send(
            target_sysid,
            target_compid,
            0,
        )
        print("[bridge] Sent MISSION_SET_CURRENT seq=0")
    except Exception as exc:
        print(f"[bridge] MISSION_SET_CURRENT failed: {exc}")

    # Demande explicite de démarrage mission.
    mav_conn.mav.command_long_send(
        target_sysid,
        target_compid,
        mavutil.mavlink.MAV_CMD_MISSION_START,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    )

    print("[bridge] Sent MAV_CMD_MISSION_START")
    wait_command_ack(mavutil.mavlink.MAV_CMD_MISSION_START)


# ============================================================
# SOCKET.IO
# ============================================================

@sio.event
def connect() -> None:
    print("[bridge] Connected to API")


@sio.event
def disconnect() -> None:
    print("[bridge] Disconnected from API")


@sio.on("connected")
def on_connected(
    payload: Dict[str, Any],
) -> None:
    global relay_device_id

    relay_device_id = payload.get("deviceId")

    print(
        "[bridge] Server auth context:",
        payload,
    )


# ============================================================
# COMMANDES
# ============================================================

@sio.on("relay:command")
def on_relay_command(
    payload: Dict[str, Any],
) -> None:
    print(
        "[bridge] relay:command received:",
        payload,
    )

    global mav_conn

    if mav_conn is None:
        print(
            "[bridge] MAVLink not ready, "
            "command ignored"
        )
        return

    label = payload.get("label")
    drone_id = payload.get("droneId")

    if not isinstance(drone_id, str):
        print(
            "[bridge] Missing droneId "
            "in relay:command payload"
        )
        return

    target = get_target_for_drone(drone_id)

    target_sysid = int(target["sysid"])
    target_compid = int(target["compid"])

    print(
        f"[bridge] Dispatch command "
        f"label={label} "
        f"to sysid={target_sysid} "
        f"compid={target_compid}"
    )

    # --------------------------------------------------------
    # ARM
    # --------------------------------------------------------

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

        print(
            "[bridge] Sent "
            "MAV_CMD_COMPONENT_ARM_DISARM (ARM)"
        )

        wait_command_ack(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
        )

        return

    # --------------------------------------------------------
    # ARM FORCE
    # --------------------------------------------------------

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

        print(
            "[bridge] Sent "
            "MAV_CMD_COMPONENT_ARM_DISARM "
            "(ARM_FORCE)"
        )

        wait_command_ack(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
        )

        return

    # --------------------------------------------------------
    # DISARM
    # --------------------------------------------------------

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

        print(
            "[bridge] Sent "
            "MAV_CMD_COMPONENT_ARM_DISARM "
            "(DISARM)"
        )

        wait_command_ack(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM
        )

        return

    # --------------------------------------------------------
    # MODES
    # --------------------------------------------------------

    if label == "GUIDED":
        send_mode_change(
            "GUIDED",
            target_sysid,
        )
        return

    if label == "STABILIZE":
        send_mode_change(
            "STABILIZE",
            target_sysid,
        )
        return

    if label in (
        "AUTO",
        "Mission Auto",
    ):
        switched = send_mode_change(
            "AUTO",
            target_sysid,
        )
        if switched:
            start_mission(
                target_sysid,
                target_compid,
            )
        else:
            print(
                "[bridge] Mission start annulé: "
                "AUTO non confirmé"
            )
        return

    if label == "START":
        start_mission(
            target_sysid,
            target_compid,
        )
        return

    if label == "Loiter":
        send_mode_change(
            "LOITER",
            target_sysid,
        )
        return

    if label == "RTL":
        send_mode_change(
            "RTL",
            target_sysid,
        )
        return

    if label == "Land":
        send_mode_change(
            "LAND",
            target_sysid,
        )
        return

    print(
        f"[bridge] Command label '{label}' "
        "received (no MAVLink mapping yet)"
    )


# ============================================================
# MISSIONS
# ============================================================

def send_mission_item_int(
    item: Dict[str, Any],
    target_sysid: int,
    target_compid: int,
) -> None:
    if mav_conn is None:
        raise RuntimeError(
            "MAVLink not ready"
        )

    frame = int(item["frame"])

    # MISSION_ITEM_INT attend les coordonnées
    # en degrés * 1e7.
    x = int(
        round(
            float(item.get("x", 0)) * 1e7
        )
    )

    y = int(
        round(
            float(item.get("y", 0)) * 1e7
        )
    )

    mav_conn.mav.mission_item_int_send(
        target_sysid,
        target_compid,

        int(item["seq"]),
        frame,
        int(item["command"]),

        int(item.get("current", 0)),
        int(item.get("autocontinue", 1)),

        float(item.get("param1", 0)),
        float(item.get("param2", 0)),
        float(item.get("param3", 0)),
        float(item.get("param4", 0)),

        x,
        y,
        float(item.get("z", 0)),

        mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
    )


def send_mission_item_float(
    item: Dict[str, Any],
    target_sysid: int,
    target_compid: int,
) -> None:
    if mav_conn is None:
        raise RuntimeError(
            "MAVLink not ready"
        )

    mav_conn.mav.mission_item_send(
        target_sysid,
        target_compid,

        int(item["seq"]),
        int(item["frame"]),
        int(item["command"]),

        int(item.get("current", 0)),
        int(item.get("autocontinue", 1)),

        float(item.get("param1", 0)),
        float(item.get("param2", 0)),
        float(item.get("param3", 0)),
        float(item.get("param4", 0)),

        float(item.get("x", 0)),
        float(item.get("y", 0)),
        float(item.get("z", 0)),

        mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
    )


def normalize_mission_items_for_ardupilot(
    items: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = [dict(item) for item in items]

    if not normalized:
        return normalized

    first = normalized[0]
    first_command = int(first.get("command", -1))
    first_frame = int(first.get("frame", -1))

    has_home_like_first_item = (
        first_command == mavutil.mavlink.MAV_CMD_NAV_WAYPOINT
        and first_frame == mavutil.mavlink.MAV_FRAME_GLOBAL
    )

    if not has_home_like_first_item:
        seed = normalized[0]

        # ArduPilot peut remplacer l'item 0 par HOME.
        # On insere un item home-like pour preserver
        # les vraies actions (ex: TAKEOFF) a partir de seq=1.
        home_like: Dict[str, Any] = {
            "seq": 0,
            "frame": mavutil.mavlink.MAV_FRAME_GLOBAL,
            "command": mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            "current": 1,
            "autocontinue": 1,
            "param1": 0,
            "param2": 0,
            "param3": 0,
            "param4": 0,
            "x": float(seed.get("x", 0)),
            "y": float(seed.get("y", 0)),
            "z": float(seed.get("z", 0)),
        }

        normalized.insert(0, home_like)

        print(
            "[bridge] Mission normalized for ArduPilot: "
            "prepended HOME-like item at seq=0"
        )

    for i, item in enumerate(normalized):
        item["seq"] = i
        item["current"] = 1 if i == 0 else 0
        item["autocontinue"] = 1 if int(item.get("autocontinue", 1)) != 0 else 0

    return normalized


def upload_mission_to_drone(
    drone_id: str,
    items: list[Dict[str, Any]],
    mission_id: str,
    timeout_sec: float = 20.0,
) -> bool:
    global mav_conn

    if mav_conn is None:
        raise RuntimeError(
            "MAVLink not ready"
        )

    if not items:
        raise ValueError(
            "Mission vide"
        )

    mission_items = normalize_mission_items_for_ardupilot(items)

    if not mission_items:
        raise ValueError(
            "Mission vide"
        )

    target = get_target_for_drone(
        drone_id
    )

    target_sysid = int(
        target["sysid"]
    )

    target_compid = int(
        target["compid"]
    )

    print(
        f"[bridge] Upload mission {mission_id} "
        f"drone={drone_id} "
        f"sysid={target_sysid} "
        f"compid={target_compid} "
        f"items={len(mission_items)}"
    )

    mission_in_progress.set()

    try:
        with mission_lock:

            # ------------------------------------------------
            # 1. Nettoyage des éventuels vieux messages
            # mission déjà présents dans la queue.
            # ------------------------------------------------

            while True:
                with mav_io_lock:
                    old_msg = mav_conn.recv_match(
                        type=[
                            "MISSION_REQUEST",
                            "MISSION_REQUEST_INT",
                            "MISSION_ACK",
                        ],
                        blocking=False,
                    )

                if old_msg is None:
                    break

            # ------------------------------------------------
            # 2. Effacement de l'ancienne mission
            # ------------------------------------------------

            mav_conn.mav.mission_clear_all_send(
                target_sysid,
                target_compid,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )

            print(
                "[bridge] MISSION_CLEAR_ALL sent"
            )

            time.sleep(0.3)

            # ------------------------------------------------
            # 3. Annonce du nombre de points
            # ------------------------------------------------

            mav_conn.mav.mission_count_send(
                target_sysid,
                target_compid,
                len(mission_items),
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )

            print(
                f"[bridge] MISSION_COUNT sent: "
                f"{len(mission_items)}"
            )

            deadline = (
                time.time() + timeout_sec
            )

            sent_sequences = set()

            # --------------------------------------------
            # 4. Attente des demandes du drone
            # --------------------------------------------

            while time.time() < deadline:

                with mav_io_lock:
                    msg = mav_conn.recv_match(
                        type=[
                            "MISSION_REQUEST_INT",
                            "MISSION_REQUEST",
                            "MISSION_ACK",
                        ],
                        blocking=True,
                        timeout=1,
                    )


                if msg is None:
                    continue

                # ----------------------------------------
                # Vérification du drone source
                # ----------------------------------------

                try:
                    source_sysid = int(
                        msg.get_srcSystem()
                    )

                    if (
                        source_sysid
                        != target_sysid
                    ):
                        continue

                except Exception:
                    pass

                msg_type = msg.get_type()

                # ----------------------------------------
                # Le drone demande un waypoint
                # ----------------------------------------

                if msg_type in (
                    "MISSION_REQUEST_INT",
                    "MISSION_REQUEST",
                ):
                    seq = int(
                        msg.seq
                    )

                    if (
                        seq < 0
                        or seq >= len(mission_items)
                    ):
                        raise RuntimeError(
                            "Drone demande "
                            f"un item invalide: {seq}"
                        )

                    item = mission_items[seq]

                    print(
                        f"[bridge] Drone requests "
                        f"mission item {seq} "
                        f"via {msg_type}"
                    )

                    if (
                        msg_type
                        == "MISSION_REQUEST_INT"
                    ):
                        send_mission_item_int(
                            item,
                            target_sysid,
                            target_compid,
                        )

                    else:
                        send_mission_item_float(
                            item,
                            target_sysid,
                            target_compid,
                        )

                    sent_sequences.add(
                        seq
                    )

                    continue

                # ----------------------------------------
                # Fin d'upload
                # ----------------------------------------

                if msg_type == "MISSION_ACK":

                    result = int(
                        msg.type
                    )

                    sent_count = len(
                        sent_sequences
                    )

                    # IMPORTANT:
                    # Un ACK peut provenir du
                    # MISSION_CLEAR_ALL juste avant l'upload.
                    # On ne valide donc la mission qu'apres
                    # l'envoi de tous les items demandes.
                    if (
                        result
                        == mavutil.mavlink.MAV_MISSION_ACCEPTED
                        and sent_count < len(mission_items)
                    ):
                        print(
                            "[bridge] Ignoring early "
                            "MISSION_ACK ACCEPTED "
                            f"({sent_count}/{len(mission_items)} items sent)"
                        )
                        continue

                    print(
                        f"[bridge] MISSION_ACK "
                        f"result={result}"
                    )

                    if (
                        result
                        == mavutil.mavlink.MAV_MISSION_ACCEPTED
                    ):
                        print(
                            f"[bridge] Mission "
                            f"{mission_id} uploaded "
                            "successfully"
                        )

                        return True

                    raise RuntimeError(
                        "Mission refusée par "
                        "autopilot: "
                        f"MAV_MISSION_RESULT={result}"
                    )

            raise TimeoutError(
                f"Timeout upload mission "
                f"{mission_id}; "
                f"items envoyés="
                f"{sorted(sent_sequences)}"
            )

    finally:
        mission_in_progress.clear()


@sio.on("relay:mission:upload")
def on_relay_mission_upload(
    payload: Dict[str, Any],
) -> None:
    mission_id = payload.get(
        "missionId"
    )

    print(
        "[bridge] relay:mission:upload "
        f"received: {mission_id}"
    )

    drone_id = payload.get(
        "droneId"
    )

    items = payload.get(
        "items"
    )

    if not isinstance(
        drone_id,
        str,
    ):
        print(
            "[bridge] mission upload "
            "missing droneId"
        )
        return

    if not isinstance(
        mission_id,
        str,
    ):
        print(
            "[bridge] mission upload "
            "missing missionId"
        )
        return

    if not isinstance(
        items,
        list,
    ):
        print(
            "[bridge] mission upload "
            "invalid items"
        )
        return

    try:
        upload_mission_to_drone(
            drone_id=drone_id,
            items=items,
            mission_id=mission_id,
        )

        sio.emit(
            "relay:mission:status",
            {
                "missionId": mission_id,
                "droneId": drone_id,
                "status": "uploaded",
                "itemCount": len(items),
                "ts": int(
                    time.time() * 1000
                ),
            },
        )

    except Exception as exc:
        print(
            "[bridge] Mission upload "
            f"failed: {exc}"
        )

        sio.emit(
            "relay:mission:status",
            {
                "missionId": mission_id,
                "droneId": drone_id,
                "status": "failed",
                "error": str(exc),
                "ts": int(
                    time.time() * 1000
                ),
            },
        )


# ============================================================
# TELEMETRIE
# ============================================================

def try_get_mode(
    msg: Any,
) -> Optional[str]:
    try:
        return mavutil.mode_string_v10(
            msg
        )

    except Exception:
        return None


def resolve_drone_id(
    msg: Any,
) -> Optional[str]:

    if drone_id_by_sysid:
        try:
            sysid = str(
                msg.get_srcSystem()
            )

        except Exception:
            return None

        return drone_id_by_sysid.get(
            sysid
        )

    if AUTO_CONFIG_FROM_API:
        try:
            sysid = str(
                msg.get_srcSystem()
            )

        except Exception:
            return None

        with runtime_map_lock:
            return (
                runtime_drone_id_by_sysid
                .get(sysid)
            )

    return DRONE_ID


# ============================================================
# CONFIG API
# ============================================================

def fetch_runtime_mapping_from_api() -> None:
    if not relay_device_id:
        return

    query = urllib.parse.urlencode(
        {
            "relayId":
                relay_device_id,
        }
    )

    url = (
        f"{API_URL.rstrip('/')}"
        f"/api/telemetry/config/by-relay?"
        f"{query}"
    )

    req = urllib.request.Request(
        url
    )

    with urllib.request.urlopen(
        req,
        timeout=5,
    ) as response:

        payload = json.loads(
            response
            .read()
            .decode("utf-8")
        )

    api_items = payload.get(
        "items",
        [],
    )

    new_mapping: Dict[str, str] = {}

    for item in api_items:
        sysid = item.get(
            "mavlinkSysId"
        )

        drone_id = item.get(
            "droneId"
        )

        if (
            isinstance(sysid, int)
            and isinstance(
                drone_id,
                str,
            )
        ):
            new_mapping[
                str(sysid)
            ] = drone_id

    with runtime_map_lock:
        runtime_drone_id_by_sysid.clear()

        runtime_drone_id_by_sysid.update(
            new_mapping
        )

    if new_mapping:
        print(
            "[bridge] Runtime mapping "
            "updated from API:",
            new_mapping,
        )


def config_poller_loop() -> None:
    while True:
        try:
            if AUTO_CONFIG_FROM_API:
                fetch_runtime_mapping_from_api()

        except Exception as exc:
            print(
                "[bridge] Failed to refresh "
                f"runtime mapping: {exc}"
            )

        time.sleep(
            CONFIG_REFRESH_SEC
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    global mav_conn

    print(
        "[bridge] API_URL:",
        API_URL,
    )

    print(
        "[bridge] DRONE_ID:",
        DRONE_ID,
    )

    if drone_id_by_sysid:
        print(
            "[bridge] DRONE_ID_BY_SYSID:",
            drone_id_by_sysid,
        )

    print(
        "[bridge] AUTO_CONFIG_FROM_API:",
        AUTO_CONFIG_FROM_API,
    )

    print(
        "[bridge] CONFIG_REFRESH_SEC:",
        CONFIG_REFRESH_SEC,
    )

    print(
        "[bridge] MAVLINK_ENDPOINT:",
        MAVLINK_ENDPOINT,
    )

    print(
        "[bridge] PUSH_HZ:",
        PUSH_HZ,
    )

    # --------------------------------------------------------
    # Connexion API
    # --------------------------------------------------------

    sio.connect(
        API_URL,
        auth={
            "apiKey":
                RELAY_API_KEY,
        },
        headers={
            "x-api-key":
                RELAY_API_KEY,
        },
        transports=[
            "websocket",
        ],
        wait_timeout=10,
    )

    # --------------------------------------------------------
    # Config dynamique droneId <-> sysid
    # --------------------------------------------------------

    if AUTO_CONFIG_FROM_API:
        t = threading.Thread(
            target=config_poller_loop,
            daemon=True,
        )

        t.start()

    # --------------------------------------------------------
    # MAVLink
    # --------------------------------------------------------

    mav = mavutil.mavlink_connection(
        MAVLINK_ENDPOINT
    )

    mav_conn = mav

    print(
        "[bridge] Waiting MAVLink heartbeat..."
    )

    mav.wait_heartbeat(
        timeout=60
    )

    print(
        "[bridge] MAVLink heartbeat received"
    )

    state_by_drone: Dict[
        str,
        Dict[str, Any],
    ] = {}

    min_interval = (
        1.0 / PUSH_HZ
    )

    last_push = 0.0

    # --------------------------------------------------------
    # BOUCLE MAVLINK
    # --------------------------------------------------------

    while True:

        # IMPORTANT :
        # pendant l'upload de mission,
        # upload_mission_to_drone() doit être
        # le seul code à lire recv_match().
        if mission_in_progress.is_set():
            time.sleep(0.05)
            continue

        with mav_io_lock:
            msg = mav.recv_match(
                blocking=True,
                timeout=1,
            )

        if msg is None:
            continue

        drone_id = resolve_drone_id(
            msg
        )

        if not drone_id:
            continue

        # ----------------------------------------------------
        # Initialisation état télémétrie
        # ----------------------------------------------------

        if drone_id not in state_by_drone:
            state_by_drone[
                drone_id
            ] = {
                "lat": None,
                "lon": None,
                "alt": None,
                "groundspeed": None,
                "mode": None,
            }

        # ----------------------------------------------------
        # Enregistre sysid / compid du drone
        # ----------------------------------------------------

        try:
            target_by_drone[
                drone_id
            ] = {
                "sysid": int(
                    msg.get_srcSystem()
                ),
                "compid": int(
                    msg.get_srcComponent()
                ),
            }

        except Exception:
            pass

        state = state_by_drone[
            drone_id
        ]

        mtype = msg.get_type()

        # ----------------------------------------------------
        # Position GPS
        # ----------------------------------------------------

        if mtype == "GLOBAL_POSITION_INT":

            state["lat"] = (
                float(msg.lat) / 1e7
            )

            state["lon"] = (
                float(msg.lon) / 1e7
            )

            state["alt"] = (
                float(
                    msg.relative_alt
                )
                / 1000.0
            )

        # ----------------------------------------------------
        # Vitesse / altitude
        # ----------------------------------------------------

        elif mtype == "VFR_HUD":

            state["groundspeed"] = float(
                msg.groundspeed
            )

            if state["alt"] is None:
                state["alt"] = float(
                    msg.alt
                )

        # ----------------------------------------------------
        # Mode
        # ----------------------------------------------------

        elif mtype == "HEARTBEAT":

            mode = try_get_mode(
                msg
            )

            if mode:
                state["mode"] = mode

        # ----------------------------------------------------
        # Limitation fréquence telemetry:push
        # ----------------------------------------------------

        now = time.time()

        if (
            now - last_push
            < min_interval
        ):
            continue

        telemetry_payload = {
            "droneId":
                drone_id,

            "ts":
                int(
                    time.time()
                    * 1000
                ),
        }

        if state["lat"] is not None:
            telemetry_payload[
                "lat"
            ] = state["lat"]

        if state["lon"] is not None:
            telemetry_payload[
                "lon"
            ] = state["lon"]

        if state["alt"] is not None:
            telemetry_payload[
                "alt"
            ] = state["alt"]

        if (
            state["groundspeed"]
            is not None
        ):
            telemetry_payload[
                "groundspeed"
            ] = state[
                "groundspeed"
            ]

        if state["mode"] is not None:
            telemetry_payload[
                "mode"
            ] = state["mode"]

        sio.emit(
            "telemetry:push",
            telemetry_payload,
        )

        print(
            "[bridge] telemetry:push",
            telemetry_payload,
        )

        last_push = now


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\n[bridge] Stopped by user"
        )

    finally:
        try:
            sio.disconnect()

        except Exception:
            pass