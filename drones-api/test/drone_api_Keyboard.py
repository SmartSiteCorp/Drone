#!/usr/bin/env python3
"""Test clavier via API Socket.IO (aucune connexion MAVLink directe).

Installation : python -m pip install -r test/requirements.txt
Dans drones-api/.env : DRONE_API_KEY="..." et DRONE_ID="uuid"
Lancement : python test/drone_api_Keyboard.py

Requiert le handler control.ts décrit dans la conversation et un relay
qui implémente relay:control / relay:control:stop avec watchdog local.
T demande un takeoff à 3 m; le drone doit déjà être armé.
P réserve une session API sans armer le drone.
Une confirmation API de commande n'est pas une confirmation ArduPilot.
"""

import argparse
import math
import os
import queue
import threading
import time
import uuid
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv
except ImportError as exc:
    raise SystemExit("Installer les dépendances : python -m pip install -r test/requirements.txt") from exc

load_dotenv(PROJECT_ROOT / ".env", override=False)


def movement(keys, scale):
    forward = float("z" in keys) - float("s" in keys)
    right = float("d" in keys) - float("q" in keys)
    norm = max(1.0, math.hypot(forward, right))
    return {
        "forward": forward / norm * scale,
        "right": right / norm * scale,
        "vertical": (float("space" in keys) - float("x" in keys)) * scale,
        "yaw": (float("e" in keys) - float("a" in keys)) * scale,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("DRONE_API_URL", "http://localhost:7281"))
    parser.add_argument("--drone-id", default=os.getenv("DRONE_ID"))
    parser.add_argument("--scale", type=float, default=0.5, help="Amplitude des axes (0..1), défaut 0.5")
    args = parser.parse_args()
    if not 0 < args.scale <= 1:
        parser.error("--scale doit être compris entre 0 exclus et 1 inclus")
    drone_id = args.drone_id
    if not drone_id:
        parser.error("Définir DRONE_ID dans drones-api/.env ou utiliser --drone-id")
    try:
        drone_id = str(uuid.UUID(drone_id))
    except ValueError:
        parser.error("UUID du drone invalide")
    api_key = os.getenv("DRONE_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        parser.error("Définir DRONE_API_KEY (scope commands:write) dans drones-api/.env")

    try:
        import pygame
        import socketio
        from pynput import keyboard
    except ImportError:
        raise SystemExit("Installer les dépendances : python -m pip install -r test/requirements.txt")

    # Les callbacks réseau placent leurs résultats dans une file.
    # Tous les emit sont exécutés dans la boucle principale, sans appels concurrents.
    notifications = queue.SimpleQueue()
    sio = socketio.Client(reconnection=False, logger=False, engineio_logger=False)
    sio.on("disconnect", lambda *a: notifications.put(("disconnect", None)))
    sio.on("drone:control:ended", lambda data: notifications.put(("ended", data)))
    sio.on("commande:status", lambda data: notifications.put(("command_status", data)))
    sio.on("connect_error", lambda data: notifications.put(("connect_error", None)))

    try:
        sio.connect(args.url, auth={"apiKey": api_key}, transports=["websocket"], wait_timeout=8)
    except Exception as exc:
        raise SystemExit(f"Connexion impossible ({type(exc).__name__}). Vérifier URL, clé et serveur Socket.IO.")

    pygame.init()
    screen = pygame.display.set_mode((880, 520))
    pygame.display.set_caption("Drone - test API Socket.IO (clavier)")
    font = pygame.font.SysFont("consolas", 19)
    clock = pygame.time.Clock()
    keys = set()
    session_id = None
    pending_start = None
    start_deadline = 0.0
    seq = 0
    last_send = 0.0
    last_axes = None
    last_command = -100.0
    status = "Connecté. Raccourcis commandes globaux actifs."
    running = True

    def stop(reason="Pilotage arrêté"):
        nonlocal session_id, pending_start, status, last_axes
        old_session = session_id
        session_id = None
        pending_start = None
        keys.clear()
        with pressed_lock:
            globally_pressed.difference_update(global_movement_keys)
        last_axes = None
        if old_session and sio.connected:
            sio.emit("drone:control:stop", {"sessionId": old_session})
        status = reason

    def command(label):
        nonlocal last_command, status
        if not sio.connected:
            return
        if time.monotonic() - last_command < 0.8:
            status = "Attendre 0.8 s entre commandes ponctuelles."
            return
        if label in ("Land", "RTL", "DISARM"):
            stop()
        last_command = time.monotonic()
        sio.emit("commande:send", {"droneId": drone_id, "label": label},
                 callback=lambda data: notifications.put(("command_ack", data)))
        status = f"Commande {label} envoyée (attente de l'API)."

    key_names = {pygame.K_z: "z", pygame.K_s: "s", pygame.K_q: "q", pygame.K_d: "d",
                 pygame.K_a: "a", pygame.K_e: "e", pygame.K_SPACE: "space", pygame.K_x: "x"}
    global_movement_keys = {"z", "s", "q", "d", "a", "e", "x", "space"}
    global_command_keys = {
        "g": "GUIDED",
        "r": "ARM",
        "f": "ARM_FORCE",
        "t": "TAKEOFF",
        "l": "Land",
        "h": "RTL",
        "u": "DISARM",
    }
    globally_pressed = set()
    pressed_lock = threading.Lock()

    def get_global_key_name(key):
        if key == keyboard.Key.space:
            return "space"
        try:
            return key.char.lower()
        except (AttributeError, TypeError):
            return None

    def request_control_start(now):
        nonlocal pending_start, start_deadline, status
        if session_id or pending_start or not sio.connected:
            return

        keys.clear()
        with pressed_lock:
            globally_pressed.difference_update(global_movement_keys)
        request_id = str(uuid.uuid4())
        pending_start = request_id
        start_deadline = now + 2.0
        sio.emit(
            "drone:control:start",
            {"droneId": drone_id},
            callback=lambda data, rid=request_id: notifications.put(("start", (rid, data))),
        )
        status = "Demande de session API..."

    def on_global_key_press(key):
        pressed_key = get_global_key_name(key)
        if pressed_key is None:
            return

        if pressed_key in global_movement_keys:
            with pressed_lock:
                globally_pressed.add(pressed_key)
            return

        if pressed_key in ("p", "m"):
            with pressed_lock:
                if pressed_key in globally_pressed:
                    return
                globally_pressed.add(pressed_key)
            notifications.put(("global_action", pressed_key))
            return

        label = global_command_keys.get(pressed_key)
        if label is None:
            return

        with pressed_lock:
            if pressed_key in globally_pressed:
                return
            globally_pressed.add(pressed_key)

        notifications.put(("global_command", label))

    def on_global_key_release(key):
        pressed_key = get_global_key_name(key)
        if pressed_key is None:
            return

        with pressed_lock:
            globally_pressed.discard(pressed_key)

    hotkey_listener = keyboard.Listener(
        on_press=on_global_key_press,
        on_release=on_global_key_release,
    )
    hotkey_listener.start()

    try:
        while running:
            now = time.monotonic()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.WINDOWFOCUSLOST:
                    keys.clear()
                    last_axes = None
                    status = "Fenêtre inactive : touches globales actives."
                elif event.type == pygame.KEYUP:
                    keys.discard(key_names.get(event.key))
                elif event.type == pygame.KEYDOWN and not getattr(event, "repeat", False):
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key in key_names and session_id:
                        keys.add(key_names[event.key])

            while not notifications.empty():
                kind, data = notifications.get()
                if kind == "disconnect":
                    stop("API déconnectée. Relancer le script pour reconnecter.")
                elif kind == "start":
                    rid, result = data
                    result = result if isinstance(result, dict) else {}
                    sid = result.get("sessionId")
                    if rid != pending_start or now >= start_deadline:
                        if sid and sio.connected:
                            sio.emit("drone:control:stop", {"sessionId": sid})
                        if rid == pending_start:
                            pending_start = None
                            status = "Demande expirée. P pour réessayer."
                    else:
                        pending_start = None
                        if result.get("ok") and sid:
                            session_id = sid
                            seq = 0
                            keys.clear()
                            last_axes = None
                            status = "Session API active. Vérifier GUIDED côté drone."
                        else:
                            status = str(result.get("error", "Réponse API invalide"))
                elif kind == "ended" and isinstance(data, dict) and data.get("sessionId") == session_id:
                    stop("Session terminée : " + str(data.get("reason", "inconnue")))
                elif kind == "command_ack":
                    if isinstance(data, dict) and data.get("ok"):
                        status = "Commande acceptée par l'API ; vérifier son exécution sur le drone."
                    else:
                        status = "Commande refusée : " + str(data.get("error", "inconnue") if isinstance(data, dict) else "réponse invalide")
                elif kind == "command_status":
                    print("Statut commande :", data)
                elif kind == "global_command":
                    command(data)
                elif kind == "global_action":
                    if data == "p":
                        request_control_start(now)
                    elif data == "m":
                        stop()

            if pending_start and now >= start_deadline:
                pending_start = None
                status = "Pas de réponse à start : vérifier le handler control.ts. P pour réessayer."

            with pressed_lock:
                global_keys = {
                    key for key in globally_pressed if key in global_movement_keys
                }
            axes = movement(keys | global_keys, args.scale)
            # 20 Hz, plus envoi au changement de touches. Aucun rattrapage
            # des ticks manqués : on n'envoie que l'état courant.
            if session_id and sio.connected and (now - last_send >= 0.05 or axes != last_axes):
                seq += 1
                sio.emit("drone:control", {"sessionId": session_id, "seq": seq, **axes})
                last_send = now
                last_axes = axes.copy()

            screen.fill((18, 24, 35))
            lines = ["TEST CLAVIER VIA API SOCKET.IO", f"API : {args.url}", f"Drone : {drone_id}",
                     "", "P : démarrer session    M : arrêter    Échap : quitter",
                     "Raccourcis globaux : G GUIDED  R ARM  F ARM FORCE  T takeoff 3 m",
                     "L LAND  H RTL  U désarmer | P/M + mouvement actifs en arrière-plan",
                     "Z/S : avant/arrière    Q/D : gauche/droite",
                     "A/E : rotation         Espace/X : monter/descendre (global)",
                     f"Amplitude : {args.scale:.2f} (vitesses définies par le relay)",
                     "", f"Session : {'ACTIVE' if session_id else 'INACTIVE'} | Paquets : {seq}",
                     "Axes : " + "  ".join(f"{k}={v:+.2f}" for k, v in axes.items()),
                     "", status, "", "Aucun décollage automatique."]
            for index, line in enumerate(lines):
                color = (100, 220, 170) if index in (0, 12) else (225, 230, 240)
                screen.blit(font.render(line, True, color), (18, 18 + index * 26))
            pygame.display.flip()
            clock.tick(120)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            stop("Fermeture")
            time.sleep(0.1)
        finally:
            hotkey_listener.stop()
            if sio.connected:
                sio.disconnect()
            pygame.quit()


if __name__ == "__main__":
    main()
