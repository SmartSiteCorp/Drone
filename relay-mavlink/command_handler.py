"""
Module de traitement des commandes relay reçues via Socket.IO
"""
import time
from typing import Dict, Any, Optional
from pymavlink import mavutil
from mission_controller import MissionController


class CommandHandler:
    def __init__(self, mav_connection: mavutil.mavfile, drone_id: str):
        """
        Initialise le gestionnaire de commandes.
        
        Args:
            mav_connection: La connexion MAVLink active
            drone_id: L'identifiant du drone
        """
        self.mav = mav_connection
        self.drone_id = drone_id
        self.mission_controller = MissionController(mav_connection, drone_id)
    
    def _wait_mode(self, expected_mode: str, timeout: int = 5) -> bool:
        """
        Attend que le drone confirme le changement de mode.
        
        Args:
            expected_mode: Le mode attendu
            timeout: Timeout en secondes (défaut: 5)
            
        Returns:
            True si le mode est confirmé, False sinon
        """
        start = time.time()

        while time.time() - start < timeout:
            msg = self.mav.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
            if not msg:
                continue

            current_mode = mavutil.mode_string_v10(msg)

            if current_mode.upper() == expected_mode.upper():
                print(f"[command_handler] Mode confirmé : {current_mode}")
                return True

        print(f"[command_handler] Timeout : mode {expected_mode} non atteint")
        return False
    
    def handle_command(self, data: Dict[str, Any]) -> None:
        """
        Traite une commande relay:command reçue.
        
        Args:
            data: Les données de la commande (format: {command: str, params: dict})
        """
        print(f"[command_handler] relay:command reçu: {data}")
        
        command = data.get("label").upper()
        params = data.get("params", {})
        
        match command:
            case "ARM":
                self._arm_disarm(True)
            case "DISARM":
                self._arm_disarm(False)
            case "SET_MODE":
                if mode := params.get("mode"):
                    self._set_mode(mode)
            case "TAKEOFF":
                altitude = params.get("altitude", 10)
                self._takeoff(altitude)
            case "RTL":
                self._rtl()
            case "LAND":
                self._land()
            case "GOTO":
                if (lat := params.get("lat")) and (lon := params.get("lon")) and (alt := params.get("alt")):
                    self._goto(lat, lon, alt)
            case "MISSION AUTO":
                self._start_auto_mission()
            case "LOITER":
                self._set_mode("LOITER")  
            case "MOTOR_TEST":
                percent = data.get("percent")
                duration_seconds = data.get("durationSeconds")
                motor = data.get("motor", "ALL")

                if percent is None or duration_seconds is None:
                    print("[command_handler] MOTOR_TEST: paramètres manquants")
                    return

                self._motor_test(
                    percent=float(percent),
                    duration_seconds=float(duration_seconds),
                    motor=motor
                )
            case _:
                print(f"[command_handler] Commande inconnue: {command}")
    
    def _arm_disarm(self, arm: bool) -> None:
        """Arme ou désarme le drone."""
        print(f"[command_handler] {'Armement' if arm else 'Désarmement'} du drone")
        self.mav.mav.command_long_send(
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1 if arm else 0,  # param1: 1=arm, 0=disarm
            0, 0, 0, 0, 0, 0
        )
    
    def _set_mode(self, mode: str) -> None:
        """Change le mode de vol."""
        print(f"[command_handler] Changement de mode: {mode}")
        # Récupère le mapping des modes
        if mode.upper() not in self.mav.mode_mapping():
            mode_id = self.mav.mode_mapping().get(mode, None)
            if mode_id is None:
                print(f"[command_handler] Mode inconnu: {mode}")
                return
        else:
            mode_id = self.mav.mode_mapping()[mode.upper()]
        
        self.mav.set_mode(mode_id)
        
        # Attend la confirmation du changement de mode
        self._wait_mode(mode)
    
    def _takeoff(self, altitude: float) -> None:
        """Décollage à une altitude donnée (en mètres)."""
        print(f"[command_handler] Décollage à {altitude}m")
        self.mav.mav.command_long_send(
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0, 0, 0, 0, 0, 0,
            altitude
        )
    
    def _rtl(self) -> None:
        """Return to Launch."""
        print(f"[command_handler] RTL (Return to Launch)")
        self._set_mode("RTL")
    
    def _land(self) -> None:
        """Atterrissage."""
        print(f"[command_handler] LAND")
        self._set_mode("LAND")
    
    def _goto(self, lat: float, lon: float, alt: float) -> None:
        """Va à une position GPS donnée."""
        print(f"[command_handler] GOTO lat={lat}, lon={lon}, alt={alt}")
        self.mav.mav.mission_item_send(
            self.mav.target_system,
            self.mav.target_component,
            0,  # seq
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            2,  # current (2 = guided mode target)
            1,  # autocontinue
            0, 0, 0, 0,  # params 1-4
            lat, lon, alt
        )
    
    def _start_auto_mission(self) -> None:
        """Lance une mission automatique complète via le MissionController."""
        success = self.mission_controller.start_auto_mission()
        if success:
            print(f"[command_handler] Mission lancée avec succès")
    def _motor_test(
        self,
        percent: float,
        duration_seconds: float,
        motor="ALL"
    ) -> None:
        """
        Teste un moteur précis ou tous les moteurs un par un.
        """

        if not 0 <= percent <= 100:
            print(f"[command_handler] Pourcentage invalide: {percent}")
            return

        if not 0 < duration_seconds <= 600:
            print(f"[command_handler] Durée invalide: {duration_seconds}")
            return

        motor_normalized = str(motor).upper()

        if motor_normalized == "ALL":
            motors = [1, 2, 3, 4]
        else:
            try:
                motor_number = int(motor)
            except (TypeError, ValueError):
                print("[command_handler] Numéro de moteur invalide")
                return

            if motor_number not in [1, 2, 3, 4]:
                print("[command_handler] Numéro de moteur invalide")
                return

            motors = [motor_number]

        for motor_number in motors:
            print(
                f"[command_handler] Test moteur {motor_number} "
                f"à {percent}% pendant {duration_seconds}s"
            )

            self.mav.mav.command_long_send(
                self.mav.target_system,
                self.mav.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
                0,
                motor_number,       # param1 : numéro moteur
                0,                  # param2 : 0 = pourcentage
                percent,            # param3 : puissance
                duration_seconds,   # param4 : durée
                1,                  # param5 : 1 moteur
                0,                  # param6
                0                   # param7
            )

            if motor_normalized == "ALL":
                time.sleep(duration_seconds + 0.5)

        print("[command_handler] Motor test terminé")  
