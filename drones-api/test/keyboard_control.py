import json
import math
import time
import threading

from datetime import datetime
from pathlib import Path

from pymavlink import mavutil
from pynput import keyboard


# ============================================================
# CONFIGURATION
# ============================================================

MAVLINK_CONNECTION = "udpin:0.0.0.0:14551"

# Déplacement manuel
SPEED_XY = 3.0
SPEED_Z = 1.5
YAW_RATE_DEG = 45.0

TAKEOFF_ALTITUDE = 3.0

CONTROL_HZ = 20


# ============================================================
# ENREGISTREMENT DE TRAJET
# ============================================================

MISSIONS_DIR = Path("recorded_missions")

# On regarde la télémétrie toutes les 0.25 s
ROUTE_SAMPLE_INTERVAL = 0.25

# Mais on ne crée pas un waypoint tous les 20 cm.
MIN_WAYPOINT_DISTANCE_M = 1.0

# Sauvegarder aussi si l'altitude change suffisamment
MIN_ALTITUDE_CHANGE_M = 0.5

# Sauvegarder aussi un point après ce délai même si peu déplacé
MAX_TIME_BETWEEN_POINTS = 2.0


# ============================================================
# MAVLINK
# ============================================================

print("Connexion MAVLink...")

master = mavutil.mavlink_connection(
    MAVLINK_CONNECTION
)

print("Attente heartbeat ArduPilot...")

heartbeat = master.wait_heartbeat(timeout=15)

if heartbeat is None:
    raise RuntimeError(
        "Aucun heartbeat reçu sur le port 14551"
    )

print(
    f"ArduPilot connecté ! "
    f"System={master.target_system}, "
    f"Component={master.target_component}"
)


# ============================================================
# DEMANDE TELEMETRIE
# ============================================================

def request_message_interval(message_id, hz):

    interval_us = int(1_000_000 / hz)

    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
        0,
        message_id,
        interval_us,
        0,
        0,
        0,
        0,
        0
    )


request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
    10
)

request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
    10
)

request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
    10
)


# ============================================================
# TELEMETRIE
# ============================================================

telemetry = {
    "global": None,
    "gps": None,
    "attitude": None
}


def update_telemetry():

    while True:

        msg = master.recv_match(blocking=False)

        if msg is None:
            break

        msg_type = msg.get_type()

        if msg_type == "GLOBAL_POSITION_INT":
            telemetry["global"] = msg

        elif msg_type == "GPS_RAW_INT":
            telemetry["gps"] = msg

        elif msg_type == "ATTITUDE":
            telemetry["attitude"] = msg


def gps_valid():

    gps = telemetry["gps"]
    global_pos = telemetry["global"]

    if gps is None or global_pos is None:
        return False

    if gps.fix_type < 3:
        return False

    if global_pos.lat == 0:
        return False

    if global_pos.lon == 0:
        return False

    return True


# ============================================================
# ETAT CLAVIER
# ============================================================

pressed_keys = set()

keyboard_lock = threading.Lock()

running = True

movement_was_active = False


# ============================================================
# RECORDING
# ============================================================

recording_route = False
route_points = []

route_lock = threading.Lock()

last_route_sample = 0


# ============================================================
# OUTILS
# ============================================================

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371000.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        +
        math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    return 2 * R * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


# ============================================================
# MODE
# ============================================================

def set_mode(mode_name):

    mapping = master.mode_mapping()

    if mode_name not in mapping:

        print(
            f"[ERREUR] Mode {mode_name} indisponible"
        )

        return

    mode_id = mapping[mode_name]

    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id
    )

    print(f"[MODE] {mode_name}")


# ============================================================
# ARM
# ============================================================

def force_arm():

    print("[ARM] FORCE ARM")

    master.mav.command_long_send(
        master.target_system,
        master.target_component,

        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,

        0,

        1,

        # code FORCE ARM ArduPilot
        21196,

        0,
        0,
        0,
        0,
        0
    )


def normal_disarm():

    print("[ARM] DISARM")

    master.mav.command_long_send(
        master.target_system,
        master.target_component,

        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,

        0,

        0,
        0,

        0,
        0,
        0,
        0,
        0
    )


def guided_and_arm():

    print("\n[GUIDED + FORCE ARM]")

    set_mode("GUIDED")

    time.sleep(0.3)

    force_arm()


# ============================================================
# TAKEOFF
# ============================================================

def takeoff(altitude):

    print(
        f"[TAKEOFF] {altitude:.1f} m"
    )

    set_mode("GUIDED")

    time.sleep(0.2)

    master.mav.command_long_send(
        master.target_system,
        master.target_component,

        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,

        0,

        0,
        0,
        0,
        0,

        0,
        0,

        altitude
    )


# ============================================================
# DEPLACEMENT
# ============================================================

def send_body_velocity(
    vx,
    vy,
    vz,
    yaw_rate
):

    type_mask = (
        1
        | 2
        | 4
        | 64
        | 128
        | 256
        | 1024
    )

    time_boot_ms = int(
        time.monotonic() * 1000
    ) & 0xFFFFFFFF

    master.mav.set_position_target_local_ned_send(
        time_boot_ms,

        master.target_system,
        master.target_component,

        mavutil.mavlink.MAV_FRAME_BODY_NED,

        type_mask,

        # position ignorée
        0,
        0,
        0,

        # vitesse
        vx,
        vy,
        vz,

        # accélération ignorée
        0,
        0,
        0,

        # yaw absolu ignoré
        0,

        yaw_rate
    )


# ============================================================
# ENREGISTREMENT TRAJET
# ============================================================

def capture_route_point():

    global last_route_sample

    if not recording_route:
        return

    now = time.time()

    if now - last_route_sample < ROUTE_SAMPLE_INTERVAL:
        return

    last_route_sample = now

    if not gps_valid():
        return

    global_pos = telemetry["global"]
    attitude = telemetry["attitude"]

    latitude = global_pos.lat / 1e7
    longitude = global_pos.lon / 1e7

    altitude_msl = (
        global_pos.alt / 1000.0
    )

    relative_altitude = (
        global_pos.relative_alt / 1000.0
    )

    heading = None

    if global_pos.hdg != 65535:

        heading = global_pos.hdg / 100.0

    elif attitude is not None:

        heading = (
            math.degrees(attitude.yaw) % 360
        )

    point = {

        "timestamp": datetime.now().isoformat(
            timespec="milliseconds"
        ),

        "time_unix": now,

        "latitude": latitude,
        "longitude": longitude,

        "altitude_msl": altitude_msl,
        "relative_altitude": relative_altitude,

        "heading": heading,

        "velocity_north": (
            global_pos.vx / 100.0
        ),

        "velocity_east": (
            global_pos.vy / 100.0
        ),

        "velocity_down": (
            global_pos.vz / 100.0
        )
    }

    with route_lock:

        # Toujours sauvegarder le premier
        if not route_points:

            route_points.append(point)

            print(
                "[REC] Premier point enregistré"
            )

            return

        previous = route_points[-1]

        distance = haversine_distance(
            previous["latitude"],
            previous["longitude"],
            latitude,
            longitude
        )

        altitude_delta = abs(
            relative_altitude
            -
            previous["relative_altitude"]
        )

        time_delta = (
            now
            -
            previous["time_unix"]
        )

        should_save = (
            distance >= MIN_WAYPOINT_DISTANCE_M
            or altitude_delta >= MIN_ALTITUDE_CHANGE_M
            or time_delta >= MAX_TIME_BETWEEN_POINTS
        )

        if should_save:

            route_points.append(point)

            print(
                f"[REC] WP {len(route_points):03d} | "
                f"d={distance:.1f}m | "
                f"alt={relative_altitude:.1f}m"
            )


# ============================================================
# GENERATION WAYPOINT FILE
# ============================================================

def save_waypoint_file(
    points,
    basename
):

    MISSIONS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    path = (
        MISSIONS_DIR
        /
        f"{basename}.waypoints"
    )

    if not points:
        return None

    first = points[0]

    # Approximation de l'altitude HOME MSL
    home_altitude = (
        first["altitude_msl"]
        -
        first["relative_altitude"]
    )

    # Altitude de décollage
    takeoff_altitude = max(
        TAKEOFF_ALTITUDE,
        first["relative_altitude"]
    )

    lines = []

    lines.append(
        "QGC WPL 110"
    )

    # ------------------------------------------------
    # HOME
    # ------------------------------------------------

    lines.append(
        "\t".join([
            "0",
            "1",
            "0",
            "16",
            "0",
            "0",
            "0",
            "0",
            f"{first['latitude']:.8f}",
            f"{first['longitude']:.8f}",
            f"{home_altitude:.3f}",
            "1"
        ])
    )

    # ------------------------------------------------
    # TAKEOFF
    # MAV_CMD_NAV_TAKEOFF = 22
    # FRAME 3 = GLOBAL_RELATIVE_ALT
    # ------------------------------------------------

    lines.append(
        "\t".join([
            "1",
            "0",
            "3",
            "22",
            "0",
            "0",
            "0",
            "0",
            f"{first['latitude']:.8f}",
            f"{first['longitude']:.8f}",
            f"{takeoff_altitude:.3f}",
            "1"
        ])
    )


    # ------------------------------------------------
    # WAYPOINTS
    # MAV_CMD_NAV_WAYPOINT = 16
    # ------------------------------------------------

    mission_index = 2

    for point in points:

        # Évite altitude 0 qui peut avoir
        # une signification spéciale.
        altitude = max(
            0.5,
            point["relative_altitude"]
        )

        lines.append(
            "\t".join([
                str(mission_index),
                "0",
                "3",
                "16",

                # param1..4
                "0",
                "0",
                "0",
                "0",

                f"{point['latitude']:.8f}",
                f"{point['longitude']:.8f}",
                f"{altitude:.3f}",

                "1"
            ])
        )

        mission_index += 1


    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8"
    )

    return path


# ============================================================
# JSON DETAILLE
# ============================================================

def save_json_file(
    points,
    basename
):

    MISSIONS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    path = (
        MISSIONS_DIR
        /
        f"{basename}.json"
    )

    data = {

        "created_at": datetime.now().isoformat(),

        "waypoint_count": len(points),

        "recording": {
            "sample_interval_seconds":
                ROUTE_SAMPLE_INTERVAL,

            "minimum_distance_m":
                MIN_WAYPOINT_DISTANCE_M,

            "minimum_altitude_change_m":
                MIN_ALTITUDE_CHANGE_M
        },

        "points": points
    }

    path.write_text(
        json.dumps(
            data,
            indent=4
        ),
        encoding="utf-8"
    )

    return path


# ============================================================
# START / STOP RECORDING
# ============================================================

def toggle_route_recording():

    global recording_route
    global route_points
    global last_route_sample

    # --------------------------------------
    # START
    # --------------------------------------

    if not recording_route:

        if not gps_valid():

            print(
                "[REC] Impossible : GPS invalide"
            )

            return

        with route_lock:
            route_points = []

        last_route_sample = 0

        recording_route = True

        print()
        print("================================")
        print("● ENREGISTREMENT TRAJET DEMARRE")
        print("================================")
        print()

        capture_route_point()

        return


    # --------------------------------------
    # STOP
    # --------------------------------------

    recording_route = False

    with route_lock:
        points = list(route_points)

    print()
    print("================================")
    print("■ ENREGISTREMENT TRAJET TERMINE")
    print("================================")

    print(
        f"{len(points)} points enregistrés"
    )


    if len(points) < 2:

        print(
            "Pas assez de points pour créer "
            "une mission."
        )

        return


    basename = (
        "mission_"
        +
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )


    waypoint_path = save_waypoint_file(
        points,
        basename
    )

    json_path = save_json_file(
        points,
        basename
    )


    print()
    print(
        f"Mission : {waypoint_path}"
    )

    print(
        f"Données : {json_path}"
    )

    print()


# ============================================================
# CLAVIER
# ============================================================

def on_press(key):

    global running

    # ENTER
    if key == keyboard.Key.enter:

        guided_and_arm()

        return


    # SPACE
    if key == keyboard.Key.space:

        with keyboard_lock:
            pressed_keys.add("space")

        return


    # ESC
    if key == keyboard.Key.esc:

        print("\nArrêt.")

        running = False

        return False


    try:
        char = key.char.lower()

    except AttributeError:
        return


    # Evite les répétitions automatiques
    with keyboard_lock:

        already_pressed = (
            char in pressed_keys
        )

        pressed_keys.add(char)


    if already_pressed:
        return


    # ========================================================
    # COMMANDES
    # ========================================================

    if char == "g":

        set_mode("GUIDED")


    elif char == "t":

        takeoff(
            TAKEOFF_ALTITUDE
        )


    elif char == "l":

        set_mode("LAND")


    elif char == "r":

        set_mode("RTL")


    elif char == "k":

        normal_disarm()


    # --------------------------------------------------------
    # P = START / STOP RECORDING
    # --------------------------------------------------------

    elif char == "p":

        toggle_route_recording()


def on_release(key):

    if key == keyboard.Key.space:

        with keyboard_lock:
            pressed_keys.discard("space")

        return


    try:
        char = key.char.lower()

    except AttributeError:
        return


    with keyboard_lock:
        pressed_keys.discard(char)


# ============================================================
# LISTENER
# ============================================================

listener = keyboard.Listener(
    on_press=on_press,
    on_release=on_release
)

listener.start()


# ============================================================
# AIDE
# ============================================================

print()
print("========================================")
print("        CONTROLE CLAVIER DRONE")
print("========================================")
print()
print("ENTER : GUIDED + ARM FORCE")
print("T     : décollage")
print()
print("Z/S   : avant / arrière")
print("Q/D   : gauche / droite")
print("A/E   : rotation gauche / droite")
print("SPACE : monter")
print("X     : descendre")
print()
print("P     : START / STOP enregistrement trajet")
print()
print("G     : GUIDED")
print("L     : LAND")
print("R     : RTL")
print("K     : DISARM")
print()
print("ESC   : quitter")
print()
print("========================================")
print()


# ============================================================
# BOUCLE
# ============================================================

period = 1.0 / CONTROL_HZ


try:

    while running:

        start = time.time()


        # ========================================
        # TELEMETRIE
        # ========================================

        update_telemetry()

        capture_route_point()


        # ========================================
        # CLAVIER
        # ========================================

        with keyboard_lock:

            keys = pressed_keys.copy()


        vx = 0.0
        vy = 0.0
        vz = 0.0

        yaw_rate = 0.0


        # ========================================
        # AVANT / ARRIERE
        # ========================================

        if "z" in keys:
            vx += SPEED_XY

        if "s" in keys:
            vx -= SPEED_XY


        # ========================================
        # GAUCHE / DROITE
        # ========================================

        if "q" in keys:
            vy -= SPEED_XY

        if "d" in keys:
            vy += SPEED_XY


        # ========================================
        # ALTITUDE
        # ========================================

        if "space" in keys:
            vz -= SPEED_Z

        if "x" in keys:
            vz += SPEED_Z


        # ========================================
        # YAW
        # ========================================

        if "a" in keys:

            yaw_rate -= math.radians(
                YAW_RATE_DEG
            )


        if "e" in keys:

            yaw_rate += math.radians(
                YAW_RATE_DEG
            )


        # ========================================
        # ENVOI
        # ========================================

        movement_active = (
            vx != 0
            or vy != 0
            or vz != 0
            or yaw_rate != 0
        )


        if movement_active:

            send_body_velocity(
                vx,
                vy,
                vz,
                yaw_rate
            )

            movement_was_active = True


        elif movement_was_active:

            send_body_velocity(
                0,
                0,
                0,
                0
            )

            movement_was_active = False


        # ========================================
        # FREQUENCE
        # ========================================

        elapsed = (
            time.time() - start
        )

        remaining = (
            period - elapsed
        )

        if remaining > 0:
            time.sleep(remaining)


except KeyboardInterrupt:

    pass


finally:

    # Si tu fermes pendant un recording,
    # on sauvegarde automatiquement.

    if recording_route:

        print(
            "\nEnregistrement actif : "
            "sauvegarde avant fermeture..."
        )

        toggle_route_recording()


    send_body_velocity(
        0,
        0,
        0,
        0
    )

    listener.stop()

    print("Contrôleur terminé.")