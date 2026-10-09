import airsim
import csv
import time
import math

from datetime import datetime
from pathlib import Path
from pymavlink import mavutil


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path("tests")

CAMERA_NAME = "down"
VEHICLE_NAME = "Copter"

PHOTO_INTERVAL = 1.0

# Python tourne sous Windows.
# ArduPilot envoie vers Windows:14550
MAVLINK_CONNECTION = "udpin:0.0.0.0:14550"

# Fréquence de télémétrie demandée à ArduPilot
TELEMETRY_RATE_HZ = 10


# ============================================================
# DOSSIER DU TEST
# ============================================================

def create_test_folder():

    BASE_DIR.mkdir(exist_ok=True)

    index = 1

    while True:

        test_dir = BASE_DIR / f"test_{index:03d}"

        if not test_dir.exists():
            break

        index += 1

    photos_dir = test_dir / "photos"

    test_dir.mkdir()
    photos_dir.mkdir()

    return test_dir, photos_dir


test_dir, photos_dir = create_test_folder()

csv_path = test_dir / "telemetry.csv"


print(f"Test       : {test_dir}")
print(f"Photos     : {photos_dir}")
print(f"Télémétrie : {csv_path}")


# ============================================================
# AIRSIM
# ============================================================

print("\nConnexion AirSim...")

client = airsim.MultirotorClient()
client.confirmConnection()

print("AirSim connecté.")


# ============================================================
# MAVLINK
# ============================================================

print("\nConnexion MAVLink...")

master = mavutil.mavlink_connection(
    MAVLINK_CONNECTION
)

print("Attente heartbeat ArduPilot...")

heartbeat = master.wait_heartbeat(timeout=15)

if heartbeat is None:
    raise RuntimeError(
        "Aucun heartbeat MAVLink reçu sur le port 14550."
    )

print(
    f"ArduPilot connecté : "
    f"system={master.target_system}, "
    f"component={master.target_component}"
)


# ============================================================
# DEMANDE DES MESSAGES MAVLINK
# ============================================================

def request_message_interval(message_id, frequency_hz):

    interval_us = int(1_000_000 / frequency_hz)

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


# GPS brut
request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
    TELEMETRY_RATE_HZ
)

# Position GPS estimée
request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
    TELEMETRY_RATE_HZ
)

# Position locale NED
request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED,
    TELEMETRY_RATE_HZ
)

# Orientation du drone
request_message_interval(
    mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
    TELEMETRY_RATE_HZ
)


print("Flux télémétrie demandé à 10 Hz.")


# ============================================================
# STOCKAGE DERNIÈRE TÉLÉMÉTRIE
# ============================================================

telemetry = {
    "gps_raw": None,
    "global": None,
    "local": None,
    "attitude": None
}


def update_telemetry():

    while True:

        msg = master.recv_match(blocking=False)

        if msg is None:
            break

        msg_type = msg.get_type()

        if msg_type == "GPS_RAW_INT":
            telemetry["gps_raw"] = msg

        elif msg_type == "GLOBAL_POSITION_INT":
            telemetry["global"] = msg

        elif msg_type == "LOCAL_POSITION_NED":
            telemetry["local"] = msg

        elif msg_type == "ATTITUDE":
            telemetry["attitude"] = msg


# ============================================================
# VALIDATION GPS
# ============================================================

def gps_is_valid():

    gps = telemetry["gps_raw"]
    global_position = telemetry["global"]

    if gps is None:
        return False

    if global_position is None:
        return False

    # 3 = 3D Fix
    if gps.fix_type < 3:
        return False

    # Pour notre simulation en France :
    # jamais accepter une position 0,0
    if gps.lat == 0 or gps.lon == 0:
        return False

    if global_position.lat == 0 or global_position.lon == 0:
        return False

    return True


# ============================================================
# ATTENTE GPS VALIDE
# ============================================================

print("\nAttente d'un GPS valide...")

last_message = 0

while True:

    update_telemetry()

    gps = telemetry["gps_raw"]

    if gps_is_valid():

        print("\nGPS VALIDE")

        print(
            f"Latitude  : {gps.lat / 1e7:.7f}"
        )

        print(
            f"Longitude : {gps.lon / 1e7:.7f}"
        )

        print(
            f"Fix       : {gps.fix_type}"
        )

        print(
            f"Satellites: {gps.satellites_visible}"
        )

        break

    if time.time() - last_message > 1:

        if gps is None:

            print("En attente de GPS_RAW_INT...")

        else:

            print(
                f"GPS non valide : "
                f"fix={gps.fix_type} | "
                f"lat={gps.lat / 1e7:.7f} | "
                f"lon={gps.lon / 1e7:.7f} | "
                f"sat={gps.satellites_visible}"
            )

        last_message = time.time()

    time.sleep(0.05)


# ============================================================
# CSV
# ============================================================

csv_file = open(
    csv_path,
    "w",
    newline="",
    encoding="utf-8"
)

writer = csv.writer(csv_file)


writer.writerow([

    # IMAGE
    "photo",
    "pc_timestamp",
    "airsim_timestamp_ns",

    # GPS BRUT
    "gps_fix_type",
    "satellites",
    "gps_raw_latitude",
    "gps_raw_longitude",
    "gps_raw_altitude_m",

    # POSITION ESTIMEE ARDUPILOT
    "latitude",
    "longitude",
    "altitude_msl_m",
    "relative_altitude_m",

    # POSITION LOCALE NED
    "local_north_m",
    "local_east_m",
    "local_down_m",

    # ORIENTATION DRONE
    "vehicle_roll_deg",
    "vehicle_pitch_deg",
    "vehicle_yaw_deg",

    # CAMERA AIRSIM
    "camera_x_m",
    "camera_y_m",
    "camera_z_m",

    # Quaternion caméra
    "camera_qw",
    "camera_qx",
    "camera_qy",
    "camera_qz"
])

csv_file.flush()


# ============================================================
# CAPTURE
# ============================================================

photo_number = 1

print("\n===================================")
print("CAPTURE DÉMARRÉE")
print("1 photo / seconde")
print("CTRL+C pour arrêter")
print("===================================\n")


try:

    while True:

        loop_start = time.time()

        # --------------------------------
        # METTRE A JOUR LA TELEMETRIE
        # --------------------------------

        update_telemetry()

        if not gps_is_valid():

            print(
                "GPS perdu / invalide -> aucune photo prise."
            )

            time.sleep(0.2)
            continue

        gps_raw = telemetry["gps_raw"]
        global_pos = telemetry["global"]
        local_pos = telemetry["local"]
        attitude = telemetry["attitude"]

        if local_pos is None or attitude is None:

            print(
                "Position locale / attitude indisponible..."
            )

            time.sleep(0.1)
            continue

        # --------------------------------
        # PHOTO
        # --------------------------------

        images = client.simGetImages(
            [
                airsim.ImageRequest(
                    CAMERA_NAME,
                    airsim.ImageType.Scene,
                    False,
                    True
                )
            ],
            vehicle_name=VEHICLE_NAME
        )

        if (
            not images
            or not images[0].image_data_uint8
        ):

            print("Erreur : image AirSim vide.")
            time.sleep(0.1)
            continue


        image = images[0]

        photo_name = (
            f"photo_{photo_number:06d}.png"
        )

        photo_path = photos_dir / photo_name


        airsim.write_file(
            str(photo_path),
            image.image_data_uint8
        )


        # --------------------------------
        # POSE CAMERA EXACTE AIRSIM
        # --------------------------------

        camera_position = image.camera_position
        camera_orientation = image.camera_orientation


        # --------------------------------
        # TIMESTAMP
        # --------------------------------

        timestamp = datetime.now().isoformat(
            timespec="milliseconds"
        )


        # --------------------------------
        # CSV
        # --------------------------------

        writer.writerow([

            # IMAGE
            photo_name,
            timestamp,
            image.time_stamp,

            # GPS RAW
            gps_raw.fix_type,
            gps_raw.satellites_visible,
            gps_raw.lat / 1e7,
            gps_raw.lon / 1e7,
            gps_raw.alt / 1000.0,

            # GLOBAL POSITION
            global_pos.lat / 1e7,
            global_pos.lon / 1e7,
            global_pos.alt / 1000.0,
            global_pos.relative_alt / 1000.0,

            # LOCAL POSITION NED
            local_pos.x,
            local_pos.y,
            local_pos.z,

            # ATTITUDE DRONE
            math.degrees(attitude.roll),
            math.degrees(attitude.pitch),
            math.degrees(attitude.yaw),

            # CAMERA POSITION AIRSIM
            camera_position.x_val,
            camera_position.y_val,
            camera_position.z_val,

            # CAMERA QUATERNION
            camera_orientation.w_val,
            camera_orientation.x_val,
            camera_orientation.y_val,
            camera_orientation.z_val
        ])

        csv_file.flush()


        # --------------------------------
        # LOG
        # --------------------------------

        latitude = global_pos.lat / 1e7
        longitude = global_pos.lon / 1e7

        print(
            f"[{photo_number:06d}] "
            f"{photo_name} | "
            f"GPS={latitude:.7f},"
            f"{longitude:.7f} | "
            f"Alt={global_pos.relative_alt / 1000:.2f}m | "
            f"NED=({local_pos.x:.2f}, "
            f"{local_pos.y:.2f}, "
            f"{local_pos.z:.2f})"
        )


        photo_number += 1


        # --------------------------------
        # 1 PHOTO / SECONDE
        # --------------------------------

        elapsed = time.time() - loop_start

        remaining = PHOTO_INTERVAL - elapsed

        if remaining > 0:
            time.sleep(remaining)


except KeyboardInterrupt:

    print("\nCapture arrêtée.")


finally:

    csv_file.close()

    print()
    print(f"Photos : {photos_dir}")
    print(f"CSV    : {csv_path}")