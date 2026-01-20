"""
================================================================================
                    MANEJADOR DE SESIONES CON REDIS
================================================================================
"""

import redis
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from config import get_settings
from database.models import Conversacion, Carrito, CanalMensaje, MensajeChat


class SessionManager:
    """Manejador de sesiones de conversación usando Redis"""
    
    SESSION_TTL = 60 * 60 * 24  # 24 horas en segundos
    
    def __init__(self):
        self.settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._local_sessions: Dict[str, dict] = {}  # Fallback sin Redis
        self._connect()
    
    def _connect(self):
        """Conecta a Redis"""
        try:
            self._redis = redis.from_url(
                self.settings.redis_url,
                decode_responses=True
            )
            # Test connection
            self._redis.ping()
            print(f"Conectado a Redis: {self.settings.redis_url}")
        except Exception as e:
            print(f"Redis no disponible: {e}")
            print("   Usando almacenamiento local en memoria")
            self._redis = None
    
    @property
    def is_connected(self) -> bool:
        return self._redis is not None
    
    def _get_session_key(self, session_id: str) -> str:
        """Genera la clave de Redis para la sesión"""
        return f"rosatel:session:{session_id}"
    
    def obtener_conversacion(
        self, 
        session_id: str,
        canal: CanalMensaje = CanalMensaje.WIDGET,
        user_id: str = None
    ) -> Conversacion:
        """
        Obtiene o crea una conversación para la sesión.
        
        Args:
            session_id: ID de la sesión
            canal: Canal de comunicación
            user_id: ID del usuario (teléfono, IG ID, etc.)
            
        Returns:
            Objeto Conversacion
        """
        key = self._get_session_key(session_id)
        
        if self._redis:
            data = self._redis.get(key)
            if data:
                return self._deserializar_conversacion(json.loads(data))
        else:
            if session_id in self._local_sessions:
                return self._deserializar_conversacion(self._local_sessions[session_id])
        
        # Crear nueva conversación
        conversacion = Conversacion(
            session_id=session_id,
            canal=canal,
            user_id=user_id,
            carrito=Carrito(session_id=session_id)
        )
        
        self.guardar_conversacion(conversacion)
        return conversacion
    
    def guardar_conversacion(self, conversacion: Conversacion):
        """
        Guarda la conversación en Redis.
        
        Args:
            conversacion: Objeto Conversacion a guardar
        """
        key = self._get_session_key(conversacion.session_id)
        data = self._serializar_conversacion(conversacion)
        
        if self._redis:
            self._redis.setex(
                key,
                self.SESSION_TTL,
                json.dumps(data)
            )
        else:
            self._local_sessions[conversacion.session_id] = data
    
    def eliminar_conversacion(self, session_id: str):
        """Elimina una conversación"""
        key = self._get_session_key(session_id)
        
        if self._redis:
            self._redis.delete(key)
        else:
            self._local_sessions.pop(session_id, None)
    
    def _serializar_conversacion(self, conv: Conversacion) -> dict:
        """Serializa conversación para almacenar"""
        return {
            "session_id": conv.session_id,
            "canal": conv.canal.value,
            "user_id": conv.user_id,
            "mensajes": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "metadata": m.metadata
                }
                for m in conv.mensajes
            ],
            "carrito": {
                "session_id": conv.carrito.session_id,
                "items": [
                    {
                        "producto_id": item.producto_id,
                        "producto_nombre": item.producto_nombre,
                        "cantidad": item.cantidad,
                        "precio_unitario": item.precio_unitario,
                        "subtotal": item.subtotal
                    }
                    for item in conv.carrito.items
                ] if conv.carrito else []
            } if conv.carrito else None,
            "contexto": conv.contexto,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat()
        }
    
    def _deserializar_conversacion(self, data: dict) -> Conversacion:
        """Deserializa conversación desde almacenamiento"""
        from database.models import CarritoItem
        
        # Reconstruir mensajes
        mensajes = []
        for m in data.get("mensajes", []):
            mensajes.append(MensajeChat(
                role=m["role"],
                content=m["content"],
                timestamp=datetime.fromisoformat(m["timestamp"]),
                metadata=m.get("metadata")
            ))
        
        # Reconstruir carrito
        carrito = None
        if data.get("carrito"):
            carrito_data = data["carrito"]
            items = []
            for item_data in carrito_data.get("items", []):
                items.append(CarritoItem(**item_data))
            
            carrito = Carrito(
                session_id=carrito_data["session_id"],
                items=items
            )
        
        # Crear conversación
        return Conversacion(
            session_id=data["session_id"],
            canal=CanalMensaje(data["canal"]),
            user_id=data.get("user_id"),
            mensajes=mensajes,
            carrito=carrito,
            contexto=data.get("contexto", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"])
        )
    
    def obtener_estadisticas(self) -> Dict[str, Any]:
        """Obtiene estadísticas de sesiones activas"""
        if self._redis:
            keys = self._redis.keys("rosatel:session:*")
            return {
                "sesiones_activas": len(keys),
                "backend": "redis"
            }
        else:
            return {
                "sesiones_activas": len(self._local_sessions),
                "backend": "memoria_local"
            }


# Instancia global
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Obtiene instancia singleton del manejador de sesiones"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
