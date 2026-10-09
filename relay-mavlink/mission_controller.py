"""
Module de contrôle des missions automatiques
"""
import time
from typing import Optional, Callable
from pymavlink import mavutil


class MissionController:
    def __init__(self, mav_connection: mavutil.mavfile, drone_id: str):
        """
        Initialise le contrôleur de missions.
        
        Args:
            mav_connection: La connexion MAVLink active
            drone_id: L'identifiant du drone
        """
        self.mav = mav_connection
        self.drone_id = drone_id
        # print(f"[mission_controller] Connecté au système ID: {mav_connection.target_system}, "
        #       f"composant ID: {mav_connection.target_component}")
    
    def _set_mode(self, mode_name: str) -> bool:
        """
        Change le mode de vol.
        
        Args:
            mode_name: Nom du mode (ex: "Loiter", "AUTO", "RTL")
            
        Returns:
            True si le mode a été changé, False sinon
        """
        mode_id = self.mav.mode_mapping().get(mode_name.upper())
        if mode_id is None:
            print(f"[mission_controller] Mode {mode_name} inconnu.")
            return False
        
        self.mav.mav.set_mode_send(
            self.mav.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )
        print(f"[mission_controller] Mode demandé: {mode_name} (id: {mode_id})")
        return True
    
    def _wait_mode(self, expected_mode: str, timeout: int = 5) -> bool:
        """
        Attend que le drone confirme le changement de mode.
        
        Args:
            expected_mode: Le mode attendu
            timeout: Timeout en secondes
            
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
                print(f"[mission_controller] Mode confirmé : {current_mode}")
                return True
        
        print(f"[mission_controller] Timeout : mode {expected_mode} non atteint")
        return False
    
    def start_auto_mission(self, callback: Optional[Callable] = None) -> bool:
        """
        Lance une mission automatique complète :
        1. Passer en mode Loiter
        2. Armer le drone
        3. Passer en mode AUTO
        4. Lancer la mission
        5. (Optionnel) Surveiller l'état de la mission
        
        Args:
            callback: Fonction de callback appelée à la fin de la mission
            
        Returns:
            True si la mission a démarré avec succès, False sinon
        """
        print("[mission_controller] Démarrage de la mission automatique...")
        
        # Étape 1 : Passer en mode Loiter pour armer
        if not self._set_mode("Loiter"):
            return False
        if not self._wait_mode("Loiter"):
            return False
        
        # Étape 2 : Armer
        print("[mission_controller] Armement du drone...")
        try:
            self.mav.arducopter_arm()
            self.mav.motors_armed_wait()
            print("[mission_controller] Drone armé.")
        except Exception as e:
            print(f"[mission_controller] Erreur lors de l'armement : {e}")
            return False
        
        time.sleep(1)
        
        # Étape 3 : Passer en mode AUTO
        if not self._set_mode("AUTO"):
            return False
        if not self._wait_mode("AUTO"):
            return False
        
        # Étape 4 : Lancer la mission
        print("[mission_controller] Lancement de la mission...")
        self.mav.mav.command_long_send(
            self.mav.target_system,
            self.mav.target_component,
            mavutil.mavlink.MAV_CMD_MISSION_START,
            0,   # Confirmation
            0,   # Première séquence à exécuter
            0,   # Dernière (0 = tous)
            0, 0, 0, 0, 0
        )
        print("[mission_controller] Mission lancée.")
        
        return True
    
    def monitor_mission(self, callback: Optional[Callable] = None) -> None:
        """
        Surveille l'état de la mission jusqu'au désarmement.
        
        Args:
            callback: Fonction appelée lorsque la mission se termine (désarmement)
        """
        print("[mission_controller] Surveillance de la mission...")
        
        while True:
            msg = self.mav.recv_match(type='HEARTBEAT', blocking=True, timeout=5)
            if not msg:
                continue
            
            armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
            mode = mavutil.mode_string_v10(msg)
            
            print(f"[mission_controller] Mode: {mode} | Armé: {armed}")
            
            if not armed:
                print("[mission_controller] Drone désarmé, fin de mission détectée.")
                if callback:
                    callback()
                break
    
    def notify_mission_finished(self, api_url: Optional[str] = None) -> None:
        """
        Envoie une notification au backend à la fin de la mission.
        
        Args:
            api_url: URL de l'API pour la notification (optionnel)
        """
        try:
            if api_url:
                import requests
                response = requests.post(
                    api_url,
                    json={"droneId": self.drone_id, "status": "done"}
                )
                print(f"[mission_controller] Notification envoyée. Code HTTP: {response.status_code}")
            else:
                print("[mission_controller] Mission terminée (pas d'URL de notification configurée)")
        except Exception as e:
            print(f"[mission_controller] Erreur lors de l'envoi de la notification : {e}")
