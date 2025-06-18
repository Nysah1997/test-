
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

class TimeTracker:
    def __init__(self, data_file: str = "user_times.json"):
        self.data_file = data_file
        self.data = self.load_data()

    def load_data(self) -> Dict[str, Any]:
        """Cargar datos desde el archivo JSON"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error cargando datos: {e}")
            return {}

    def save_data(self) -> None:
        """Guardar datos al archivo JSON"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando datos: {e}")

    def start_tracking(self, user_id: int, user_name: str) -> bool:
        """Iniciar seguimiento de tiempo para un usuario"""
        user_id_str = str(user_id)
        current_time = datetime.now().isoformat()

        if user_id_str not in self.data:
            self.data[user_id_str] = {
                'name': user_name,
                'total_time': 0,
                'sessions': [],
                'is_active': False,
                'is_paused': False,
                'pause_count': 0,
                'notified_milestones': [],
                'milestone_completed': False
            }

        user_data = self.data[user_id_str]

        # Si ya está activo, no hacer nada
        if user_data.get('is_active', False):
            return False

        # Si está pausado, no permitir iniciar nuevo tracking
        if user_data.get('is_paused', False):
            return False

        # Iniciar nueva sesión
        user_data['is_active'] = True
        user_data['is_paused'] = False
        user_data['last_start'] = current_time
        user_data['name'] = user_name  # Actualizar nombre

        self.save_data()
        return True

    def stop_tracking(self, user_id: int) -> bool:
        """Detener seguimiento de tiempo para un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return False

        user_data = self.data[user_id_str]

        if not user_data.get('is_active', False):
            return False

        # Calcular tiempo de sesión
        if user_data.get('last_start'):
            session_start = datetime.fromisoformat(user_data['last_start'])
            session_time = (datetime.now() - session_start).total_seconds()
            
            # Añadir tiempo de sesión al total
            user_data['total_time'] = user_data.get('total_time', 0) + session_time

        # Marcar como inactivo
        user_data['is_active'] = False
        user_data['is_paused'] = False

        # Agregar sesión al historial
        if 'sessions' not in user_data:
            user_data['sessions'] = []

        session_record = {
            'start': user_data.get('last_start'),
            'end': datetime.now().isoformat(),
            'duration': session_time if user_data.get('last_start') else 0
        }
        user_data['sessions'].append(session_record)

        self.save_data()
        return True

    def pause_tracking(self, user_id: int) -> bool:
        """Pausar seguimiento de tiempo para un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return False

        user_data = self.data[user_id_str]

        if not user_data.get('is_active', False):
            return False

        # Calcular tiempo de sesión actual y añadirlo al total
        if user_data.get('last_start'):
            session_start = datetime.fromisoformat(user_data['last_start'])
            session_time = (datetime.now() - session_start).total_seconds()
            user_data['total_time'] = user_data.get('total_time', 0) + session_time

        # Marcar como pausado
        user_data['is_active'] = False
        user_data['is_paused'] = True
        user_data['pause_start'] = datetime.now().isoformat()
        user_data['pause_count'] = user_data.get('pause_count', 0) + 1

        self.save_data()
        return True

    def resume_tracking(self, user_id: int) -> bool:
        """Reanudar seguimiento de tiempo para un usuario pausado"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return False

        user_data = self.data[user_id_str]

        if not user_data.get('is_paused', False):
            return False

        # Reanudar seguimiento
        user_data['is_active'] = True
        user_data['is_paused'] = False
        user_data['last_start'] = datetime.now().isoformat()

        # Limpiar pause_start
        if 'pause_start' in user_data:
            del user_data['pause_start']

        self.save_data()
        return True

    def get_total_time(self, user_id: int) -> float:
        """Obtener tiempo total acumulado de un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return 0.0

        user_data = self.data[user_id_str]
        total_time = user_data.get('total_time', 0)

        # Si está activo, añadir tiempo de sesión actual
        if user_data.get('is_active', False) and user_data.get('last_start'):
            session_start = datetime.fromisoformat(user_data['last_start'])
            current_session_time = (datetime.now() - session_start).total_seconds()
            total_time += current_session_time

        return total_time

    def get_user_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Obtener datos completos de un usuario"""
        user_id_str = str(user_id)
        return self.data.get(user_id_str)

    def get_all_tracked_users(self) -> Dict[str, Any]:
        """Obtener todos los usuarios con seguimiento"""
        return self.data.copy()

    def reset_user_time(self, user_id: int) -> bool:
        """Reiniciar tiempo de un usuario a cero"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return False

        user_data = self.data[user_id_str]
        user_data['total_time'] = 0
        user_data['is_active'] = False
        user_data['is_paused'] = False
        user_data['pause_count'] = 0
        user_data['sessions'] = []
        user_data['notified_milestones'] = []
        user_data['milestone_completed'] = False

        # Limpiar campos de seguimiento
        if 'last_start' in user_data:
            del user_data['last_start']
        if 'pause_start' in user_data:
            del user_data['pause_start']

        self.save_data()
        return True

    def reset_all_user_times(self) -> int:
        """Reiniciar todos los tiempos de usuarios"""
        count = 0
        for user_id_str in list(self.data.keys()):
            user_id = int(user_id_str)
            if self.reset_user_time(user_id):
                count += 1
        return count

    def cancel_user_tracking(self, user_id: int) -> bool:
        """Cancelar completamente el seguimiento de un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return False

        # Eliminar completamente al usuario
        del self.data[user_id_str]
        self.save_data()
        return True

    def clear_all_data(self) -> bool:
        """Limpiar completamente todos los datos"""
        try:
            self.data = {}
            self.save_data()
            return True
        except Exception as e:
            print(f"Error limpiando datos: {e}")
            return False

    def add_minutes(self, user_id: int, user_name: str, minutes: int) -> bool:
        """Añadir minutos al tiempo de un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            self.data[user_id_str] = {
                'name': user_name,
                'total_time': 0,
                'sessions': [],
                'is_active': False,
                'is_paused': False,
                'pause_count': 0,
                'notified_milestones': [],
                'milestone_completed': False
            }

        user_data = self.data[user_id_str]
        user_data['total_time'] = user_data.get('total_time', 0) + (minutes * 60)
        user_data['name'] = user_name

        self.save_data()
        return True

    def subtract_minutes(self, user_id: int, minutes: int) -> bool:
        """Restar minutos del tiempo de un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return False

        user_data = self.data[user_id_str]
        current_time = user_data.get('total_time', 0)
        new_time = max(0, current_time - (minutes * 60))
        user_data['total_time'] = new_time

        self.save_data()
        return True

    def get_pause_count(self, user_id: int) -> int:
        """Obtener número de pausas de un usuario"""
        user_id_str = str(user_id)
        if user_id_str not in self.data:
            return 0
        return self.data[user_id_str].get('pause_count', 0)

    def get_paused_duration(self, user_id: int) -> float:
        """Obtener duración pausada actual de un usuario"""
        user_id_str = str(user_id)

        if user_id_str not in self.data:
            return 0.0

        user_data = self.data[user_id_str]

        if not user_data.get('is_paused', False) or not user_data.get('pause_start'):
            return 0.0

        pause_start = datetime.fromisoformat(user_data['pause_start'])
        return (datetime.now() - pause_start).total_seconds()

    def format_time_human(self, seconds: float) -> str:
        """Formatear tiempo en formato humano legible"""
        if seconds < 0:
            return "0 Segundos"

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if hours > 0:
            parts.append(f"{hours} Hora{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} Minuto{'s' if minutes != 1 else ''}")
        if secs > 0 or not parts:  # Mostrar segundos si no hay otras partes
            parts.append(f"{secs} Segundo{'s' if secs != 1 else ''}")

        return ", ".join(parts)
