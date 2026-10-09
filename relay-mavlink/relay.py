import os
import time
import threading
import queue
import concurrent.futures
from dotenv import load_dotenv
from typing import Any, Dict, Optional, Tuple

import socketio
from pymavlink import mavutil

from command_handler import CommandHandler


# -----------------------------
# Config
# -----------------------------
load_dotenv()
MAVLINK_ENDPOINT = os.getenv("MAVLINK_ENDPOINT", "COM7")
MAVLINK_BAUD = int(os.getenv("MAVLINK_BAUD", "115200"))
DRONE_ID = os.getenv("DRONE_ID", "drone-01")

DRONECONTROL_URL = os.getenv("DRONECONTROL_URL", "http://127.0.0.1:7281")
DRONECONTROL_API_KEY = os.getenv("DRONECONTROL_API_KEY", "")  # clé relay (telemetry:write)

# fréquence max d'envoi (anti-spam)
GPS_MIN_INTERVAL_S = float(os.getenv("GPS_MIN_INTERVAL_S", "0.2"))      # 5 Hz
BATT_MIN_INTERVAL_S = float(os.getenv("BATT_MIN_INTERVAL_S", "1.0"))   # 1 Hz
VFR_MIN_INTERVAL_S = float(os.getenv("VFR_MIN_INTERVAL_S", "0.2"))     # 5 Hz


# -----------------------------
# Socket.IO client
# -----------------------------
sio = socketio.Client(reconnection=True, reconnection_attempts=0)
command_handler: Optional[CommandHandler] = None
command_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="cmd")

@sio.event
def connect():
    print("[sio] connected")

@sio.event
def disconnect():
    print("[sio] disconnected")

@sio.on("relay:command")
def on_relay_command(data):
    if command_handler:
        # Exécuter la commande dans un thread séparé (non-bloquant)
        command_executor.submit(command_handler.handle_command, data)
        print(f"[sio] relay:command soumis pour traitement: {data}")
    else:
        print(f"[sio] relay:command reçu mais handler non initialisé: {data}")


def sio_emit(event: str, payload: Dict[str, Any]) -> None:
    """Emit safe (no crash if disconnected)."""
    try:
        sio.emit(event, payload)
    except Exception as e:
        print(f"[sio] emit failed for {event}: {e}")


# -----------------------------
# MAVLink helpers
# -----------------------------
def gps_fix_label(fix_type: int) -> str:
    return {
        0: "NO_GPS",
        1: "NO_FIX",
        2: "FIX_2D",
        3: "FIX_3D",
        4: "DGPS",
        5: "RTK_FLOAT",
        6: "RTK_FIXED",
    }.get(int(fix_type), f"UNKNOWN_{fix_type}")


def is_armed(base_mode: int) -> bool:
    # MAV_MODE_FLAG_SAFETY_ARMED = 128
    return (int(base_mode) & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0


def decode_sys_status_flags(msg) -> Dict[str, Any]:
    """
    SYS_STATUS contient des bits failsafe/health. Sur ArduPilot, la partie "failsafe battery"
    remonte souvent en STATUSTEXT. Ici on expose ce qu'on peut via SYS_STATUS + batterie.
    """
    # voltage_battery en mV, current_battery en cA, battery_remaining en %
    v_mv = int(getattr(msg, "voltage_battery", -1))
    c_ca = int(getattr(msg, "current_battery", -1))
    rem = int(getattr(msg, "battery_remaining", -1))

    v = (v_mv / 1000.0) if v_mv >= 0 else None
    a = (c_ca / 100.0) if c_ca >= 0 else None

    # On expose aussi "onboard_control_sensors_health" etc.
    health = int(getattr(msg, "onboard_control_sensors_health", 0))
    enabled = int(getattr(msg, "onboard_control_sensors_enabled", 0))
    present = int(getattr(msg, "onboard_control_sensors_present", 0))

    return {
        "voltage": v,
        "current": a,
        "remaining": rem if rem >= 0 else None,
        "sensors": {
            "present": present,
            "enabled": enabled,
            "health": health,
        },
    }


def set_msg_interval(mav: mavutil.mavfile, msg_id: int, hz: float) -> None:
    """Set MAVLink message interval via command."""
    interval_us = int(1_000_000 / hz) if hz > 0 else -1
    mav.mav.command_long_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        msg_id,
        interval_us,
        0, 0, 0, 0, 0,
    )


def request_streams(mav: mavutil.mavfile) -> None:
    """Request MAVLink message streams at configured frequencies."""
    # 5 Hz
    set_msg_interval(mav, mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT, 5)
    set_msg_interval(mav, mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 5)
    set_msg_interval(mav, mavutil.mavlink.MAVLINK_MSG_ID_VFR_HUD, 5)

    # 1 Hz
    set_msg_interval(mav, mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS, 1)

    # Optionnel (si dispo)
    try:
        set_msg_interval(mav, mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 2)
    except Exception:
        pass


def should_forward_statustext(text: str) -> Tuple[bool, str]:
    """
    Filtre simple EKF / failsafe / GPS / etc.
    Retourne (should_send, category).
    """
    t = (text or "").lower()

    categories = {
        "ARM": ["prearm", "arm", "arming", "arm failed", "disarm", "throttle"],
        "EKF": ["ekf", "egh", "lane switch", "inertial nav"],
        "BATTERY": ["battery", "batt", "low voltage", "failsafe: battery"],
        "GPS": ["gps", "no fix", "bad gps", "glitch"],
        "RADIO": ["failsafe: radio", "radio failsafe", "rc failsafe"],
        "MODE": ["mode", "changed to", "auto", "loiter", "rtl", "guided"],
        "COMPASS": ["compass", "mag", "magnetometer"],
        "IMU": ["imu", "gyro", "accel", "calib"],
        "RANGE": ["rangefinder", "lidar", "rngfnd"],
        "MISSION": ["mission", "waypoint", "wp", "rtl", "landing", "takeoff"],
    }

    for cat, keys in categories.items():
        if any(k in t for k in keys):
            return True, cat

    # Option debug : au début, je te conseille de tout forward
    return True, "OTHER"


def severity_label(sev: int) -> str:
    # MAV_SEVERITY (0..7)
    return {
        0: "EMERGENCY",
        1: "ALERT",
        2: "CRITICAL",
        3: "ERROR",
        4: "WARNING",
        5: "NOTICE",
        6: "INFO",
        7: "DEBUG",
    }.get(int(sev), f"SEV_{sev}")


# -----------------------------
# Threaded pipeline
# -----------------------------
Event = Tuple[str, Dict[str, Any]]  # (event_name, payload)

stop_event = threading.Event()
events_q: "queue.Queue[Event]" = queue.Queue(maxsize=2000)


def producer_mavlink(mav: mavutil.mavfile) -> None:
    """
    Thread #1: lit le flux MAVLink en continu, et pousse des "events" normalisés dans une queue.
    """
    print("[mav] producer started")
    last_mode: Optional[int] = None
    last_armed: Optional[bool] = None

    last_gps_sent = 0.0
    last_batt_sent = 0.0
    last_vfr_sent = 0.0

    while not stop_event.is_set():
        try:
            msg = mav.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue

            mtype = msg.get_type()
            now = time.time()
            ts_ms = int(now * 1000)
            # print(f"[mav] message reçu: {mtype} at {ts_ms} ms")

            # 1) GPS fix status
            if mtype == "GPS_RAW_INT":
                if (now - last_gps_sent) < GPS_MIN_INTERVAL_S:
                    continue
                last_gps_sent = now

                fix = int(getattr(msg, "fix_type", 0))
                sats = int(getattr(msg, "satellites_visible", -1))
                lat = getattr(msg, "lat", None)  # 1e7
                lon = getattr(msg, "lon", None)  # 1e7
                alt_mm = getattr(msg, "alt", None)  # mm

                payload = {
                    "droneId": DRONE_ID,
                    "ts": ts_ms,
                    "fixType": fix,
                    "fixLabel": gps_fix_label(fix),
                    "satellites": sats if sats >= 0 else None,
                    "lat": (lat / 1e7) if isinstance(lat, (int, float)) else None,
                    "lon": (lon / 1e7) if isinstance(lon, (int, float)) else None,
                    "altMSL": (alt_mm / 1000.0) if isinstance(alt_mm, (int, float)) else None,  # m
                }
                events_q.put(("telemetry:gps", payload))
                continue

            # 1bis) Altitude relative (GLOBAL_POSITION_INT)
            if mtype == "GLOBAL_POSITION_INT":
                alt_msl_mm = getattr(msg, "alt", None)           # mm (MSL)
                rel_alt_mm = getattr(msg, "relative_alt", None)  # mm (relative HOME)

                payload = {
                    "droneId": DRONE_ID,
                    "ts": ts_ms,
                    "altMSL": (alt_msl_mm / 1000.0) if isinstance(alt_msl_mm, (int, float)) else None,
                    "altRelative": (rel_alt_mm / 1000.0) if isinstance(rel_alt_mm, (int, float)) else None,
                }
                events_q.put(("telemetry:altitude", payload))
                continue


            # 2) VFR_HUD (ground speed, vertical speed, heading)
            if mtype == "VFR_HUD":
                if (now - last_vfr_sent) < VFR_MIN_INTERVAL_S:
                    continue
                last_vfr_sent = now

                ground_speed = float(getattr(msg, "groundspeed", 0.0))  # m/s
                vertical_speed = float(getattr(msg, "climb", 0.0))      # m/s (positive = monte)
                course = float(getattr(msg, "heading", 0.0))            # degrees

                payload = {
                    "droneId": DRONE_ID,
                    "ts": ts_ms,
                    "groundSpeed": ground_speed,
                    "verticalSpeed": vertical_speed,
                    "heading": course,
                }
                events_q.put(("telemetry:vfr", payload))
                continue

            # 3) Battery status / (failsafe souvent en STATUSTEXT)
            if mtype == "SYS_STATUS":
                if (now - last_batt_sent) < BATT_MIN_INTERVAL_S:
                    continue
                last_batt_sent = now

                info = decode_sys_status_flags(msg)
                events_q.put(("telemetry:battery", {"droneId": DRONE_ID, "ts": ts_ms, **info}))

                health = int(info["sensors"]["health"]) if info.get("sensors") else int(getattr(msg, "onboard_control_sensors_health", 0))
                events_q.put(("telemetry:sensors_health", {
                    "droneId": DRONE_ID,
                    "ts": ts_ms,
                    "health": health,
                    # optionnel mais souvent utile :
                    "enabled": int(info["sensors"]["enabled"]),
                    "present": int(info["sensors"]["present"]),
                }))
                continue

            # 4) EKF status report (si dispo)
            if mtype == "EKF_STATUS_REPORT":
                # On forward tel quel, utile pour dashboard
                flags = int(getattr(msg, "flags", 0))
                vel = float(getattr(msg, "velocity_variance", 0.0))
                pos_h = float(getattr(msg, "pos_horiz_variance", 0.0))
                pos_v = float(getattr(msg, "pos_vert_variance", 0.0))
                comp = float(getattr(msg, "compass_variance", 0.0))
                terr = float(getattr(msg, "terrain_alt_variance", 0.0))
                events_q.put(("telemetry:ekf", {
                    "droneId": DRONE_ID,
                    "ts": ts_ms,
                    "flags": flags,
                    "velocityVariance": vel,
                    "posHorizVariance": pos_h,
                    "posVertVariance": pos_v,
                    "compassVariance": comp,
                    "terrainAltVariance": terr,
                }))
                continue

            # 5) Mode changes + Arm/disarm via HEARTBEAT
            if mtype == "HEARTBEAT":
                cmode = int(getattr(msg, "custom_mode", 0))
                bmode = int(getattr(msg, "base_mode", 0))
                armed = is_armed(bmode)

                if last_mode is None:
                    last_mode = cmode
                if last_armed is None:
                    last_armed = armed

                if cmode != last_mode:
                    # mapping mode via ArduPilot mode mapping
                    try:
                        mode_str = mav.mode_mapping().get(cmode, str(cmode))
                    except Exception:
                        mode_str = str(cmode)

                    events_q.put(("telemetry:mode", {
                        "droneId": DRONE_ID,
                        "ts": ts_ms,
                        "customMode": cmode,
                        "mode": mode_str,
                    }))
                    last_mode = cmode

                if armed != last_armed:
                    events_q.put(("telemetry:arm", {
                        "droneId": DRONE_ID,
                        "ts": ts_ms,
                        "armed": armed,
                    }))
                    last_armed = armed

                continue

            # 6) STATUSTEXT = warnings/errors (No GPS fix, failsafe battery, EKF warnings, etc.)
            if mtype == "STATUSTEXT":
                sev = int(getattr(msg, "severity", 7))
                text = str(getattr(msg, "text", "")).strip()

                ok, category = should_forward_statustext(text)
                if ok:
                    events_q.put(("telemetry:warning", {
                        "droneId": DRONE_ID,
                        "ts": ts_ms,
                        "category": category,
                        "severity": sev,
                        "severityLabel": severity_label(sev),
                        "text": text,
                    }))
                continue

        except queue.Full:
            # Si la queue est pleine, on drop pour ne pas bloquer la lecture MAVLink.
            print("[mav] events queue full, dropping")
        except Exception as e:
            # Remonte une erreur côté dashboard
            try:
                events_q.put(("telemetry:warning", {
                    "droneId": DRONE_ID,
                    "ts": int(time.time() * 1000),
                    "category": "RELAY",
                    "severity": 3,
                    "severityLabel": "ERROR",
                    "text": f"relay exception: {e}",
                }))
            except Exception:
                pass


def consumer_socketio() -> None:
    """
    Thread #2: consomme la queue et émet vers le backend Socket.IO.
    Ici on peut choisir d'émettre en telemetry:push (ton API) ou en events dédiés.
    """
    print("[sio] consumer started")

    while not stop_event.is_set():
        try:
            event_name, payload = events_q.get(timeout=1.0)
        except queue.Empty:
            continue

        # Option A: tu envoies tout en "telemetry:push" (ton schéma actuel)
        # -> et tu différencies via des champs type/category
        if event_name in ("telemetry:gps", "telemetry:altitude", "telemetry:battery", "telemetry:sensors_health", "telemetry:ekf", "telemetry:mode", "telemetry:arm", "telemetry:vfr"):
            sio_emit("telemetry:push", {
                **payload,
                "type": event_name.split(":")[1],  # gps / battery / ekf / mode / arm / vfr
            })
        elif event_name == "telemetry:warning":
            # erreurs/warnings drone : on les push aussi, ou un event dédié
            # si tu as choisi "telemetry:error" côté serveur, utilise ça :
            sio_emit("telemetry:push", {
                **payload,
                "type": "warning",
            })
        else:
            sio_emit("telemetry:push", {**payload, "type": "unknown"})

        events_q.task_done()


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    global command_handler
    
    if not DRONECONTROL_API_KEY:
        raise SystemExit("Missing DRONECONTROL_API_KEY env var")

    print(f"[config] MAVLINK_ENDPOINT={MAVLINK_ENDPOINT}")
    print(f"[config] DRONECONTROL_URL={DRONECONTROL_URL}")
    print(f"[config] DRONE_ID={DRONE_ID}")

    # Connexion MAVLink
    mav = mavutil.mavlink_connection(MAVLINK_ENDPOINT, baud=MAVLINK_BAUD, autoreconnect=True)
    mav.wait_heartbeat(timeout=10)
    request_streams(mav)
    print("[mav] heartbeat ok")
    
    # Initialisation du gestionnaire de commandes
    command_handler = CommandHandler(mav, DRONE_ID)

    # Connexion Socket.IO (auth via header)
    try:
        sio.connect(
            DRONECONTROL_URL,
            transports=["websocket"],
            auth={"apiKey": DRONECONTROL_API_KEY},
        )
    except socketio.exceptions.ConnectionError as e:
        print(f"[sio] Impossible de se connecter au serveur: {e}")
        print("[sio] Vérifiez que le serveur est lancé et que l'API key est correcte")
        return

    t1 = threading.Thread(target=producer_mavlink, args=(mav,), daemon=True)
    t2 = threading.Thread(target=consumer_socketio, daemon=True)

    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[main] stopping...")
        stop_event.set()
        try:
            sio.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
