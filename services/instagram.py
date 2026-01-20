"""
================================================================================
                    SERVICIO INSTAGRAM MESSAGING API
================================================================================
"""

import httpx
from typing import Optional, Dict, Any, List
from config import get_settings
from database.models import Producto
from services.image_utils import convert_drive_url


class InstagramService:
    """Servicio para Instagram Messaging API"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.settings = get_settings()
        self.token = self.settings.instagram_access_token
        self.page_id = self.settings.instagram_page_id
    
    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    @property
    def messages_url(self) -> str:
        return f"{self.BASE_URL}/{self.page_id}/messages"
    
    async def enviar_mensaje_texto(
        self, 
        recipient_id: str, 
        mensaje: str
    ) -> Dict[str, Any]:
        """
        Envía un mensaje de texto.
        
        Args:
            recipient_id: ID del usuario de Instagram
            mensaje: Texto del mensaje
        """
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "text": mensaje
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_imagen(
        self, 
        recipient_id: str, 
        imagen_url: str
    ) -> Dict[str, Any]:
        """
        Envía una imagen.
        
        Args:
            recipient_id: ID del usuario
            imagen_url: URL de la imagen
        """
        # Convertir URL de Drive
        imagen_url = convert_drive_url(imagen_url) or imagen_url
        
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "url": imagen_url,
                        "is_reusable": True
                    }
                }
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_producto(
        self, 
        recipient_id: str, 
        producto: Producto
    ) -> List[Dict[str, Any]]:
        """
        Envía información de un producto.
        
        Args:
            recipient_id: ID del usuario
            producto: Objeto Producto
        """
        respuestas = []
        
        # Enviar imagen si existe
        if producto.foto:
            resp = await self.enviar_imagen(recipient_id, producto.foto)
            respuestas.append(resp)
        
        # Construir mensaje de texto
        mensaje = f"{producto.producto}\n"
        mensaje += f"{producto.categoria} - {producto.tipo}\n"
        
        if producto.color:
            mensaje += f"Color: {producto.color}\n"
        
        if producto.descuento > 0:
            mensaje += f"S/{producto.precio:.2f} -> S/{producto.precio_final:.2f} (-{producto.descuento}%)\n"
        else:
            mensaje += f"S/{producto.precio_final:.2f}\n"
        
        mensaje += "\nDisponible" if producto.stock > 0 else "\nAgotado"
        
        resp = await self.enviar_mensaje_texto(recipient_id, mensaje)
        respuestas.append(resp)
        
        return respuestas
    
    async def enviar_respuestas_rapidas(
        self, 
        recipient_id: str, 
        mensaje: str,
        opciones: List[str]
    ) -> Dict[str, Any]:
        """
        Envía mensaje con opciones de respuesta rápida.
        
        Args:
            recipient_id: ID del usuario
            mensaje: Texto del mensaje
            opciones: Lista de opciones (max 13)
        """
        quick_replies = []
        for i, opcion in enumerate(opciones[:13]):
            quick_replies.append({
                "content_type": "text",
                "title": opcion[:20],  # Max 20 chars
                "payload": f"QUICK_REPLY_{i}"
            })
        
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "text": mensaje,
                "quick_replies": quick_replies
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_template_generico(
        self, 
        recipient_id: str,
        elementos: List[Dict]
    ) -> Dict[str, Any]:
        """
        Envía un template genérico (carrusel de productos).
        
        Args:
            recipient_id: ID del usuario
            elementos: Lista de elementos del carrusel
        """
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "generic",
                        "elements": elementos[:10]  # Max 10 elementos
                    }
                }
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_carrusel_productos(
        self, 
        recipient_id: str,
        productos: List[Producto]
    ) -> Dict[str, Any]:
        """
        Envía un carrusel de productos.
        
        Args:
            recipient_id: ID del usuario
            productos: Lista de productos
        """
        elementos = []
        
        for p in productos[:10]:
            elemento = {
                "title": p.producto[:80],
                "subtitle": f"S/{p.precio_final:.2f} - {p.categoria}"[:80],
                "buttons": [
                    {
                        "type": "postback",
                        "title": "Ver más",
                        "payload": f"VER_PRODUCTO_{p.id}"
                    },
                    {
                        "type": "postback",
                        "title": "Comprar",
                        "payload": f"COMPRAR_{p.id}"
                    }
                ]
            }
            
            if p.foto:
                elemento["image_url"] = convert_drive_url(p.foto)
            
            elementos.append(elemento)
        
        return await self.enviar_template_generico(recipient_id, elementos)
    
    async def enviar_reaccion(
        self, 
        recipient_id: str,
        message_id: str,
        reaction: str = "love"
    ) -> Dict[str, Any]:
        """
        Envía una reacción a un mensaje.
        
        Args:
            recipient_id: ID del usuario
            message_id: ID del mensaje a reaccionar
            reaction: Emoji de reacción
        """
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "sender_action": "react",
            "payload": {
                "message_id": message_id,
                "reaction": reaction
            }
        }
        
        return await self._send_request(payload)
    
    async def marcar_visto(self, recipient_id: str) -> Dict[str, Any]:
        """Marca la conversación como vista"""
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "sender_action": "mark_seen"
        }
        
        return await self._send_request(payload)
    
    async def mostrar_escribiendo(self, recipient_id: str) -> Dict[str, Any]:
        """Muestra indicador de escritura"""
        payload = {
            "recipient": {
                "id": recipient_id
            },
            "sender_action": "typing_on"
        }
        
        return await self._send_request(payload)
    
    async def _send_request(self, payload: dict) -> Dict[str, Any]:
        """Envía request a la API de Instagram"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.messages_url,
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            print(f"Error HTTP Instagram: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
            return {"error": str(e), "status_code": e.response.status_code}
            
        except Exception as e:
            print(f"Error Instagram: {e}")
            return {"error": str(e)}
    
    def parsear_webhook(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        Parsea datos del webhook de Instagram.
        
        Args:
            data: Datos del webhook
            
        Returns:
            Dict con mensaje parseado o None
        """
        try:
            entry = data.get("entry", [{}])[0]
            messaging = entry.get("messaging", [{}])[0]
            
            sender_id = messaging.get("sender", {}).get("id")
            recipient_id = messaging.get("recipient", {}).get("id")
            timestamp = messaging.get("timestamp")
            
            resultado = {
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "timestamp": timestamp,
                "type": None,
                "text": None
            }
            
            # Mensaje de texto
            message = messaging.get("message", {})
            if message:
                resultado["message_id"] = message.get("mid")
                resultado["text"] = message.get("text")
                resultado["type"] = "text"
                
                # Quick reply
                quick_reply = message.get("quick_reply")
                if quick_reply:
                    resultado["quick_reply_payload"] = quick_reply.get("payload")
                    resultado["type"] = "quick_reply"
                
                # Attachments (imágenes, stickers, etc.)
                attachments = message.get("attachments", [])
                if attachments:
                    attachment = attachments[0]
                    resultado["attachment_type"] = attachment.get("type")
                    resultado["attachment_url"] = attachment.get("payload", {}).get("url")
                    resultado["type"] = "attachment"
                    
                    if not resultado["text"]:
                        resultado["text"] = f"[{attachment.get('type', 'archivo')} recibido]"
            
            # Postback (botones)
            postback = messaging.get("postback")
            if postback:
                resultado["postback_payload"] = postback.get("payload")
                resultado["postback_title"] = postback.get("title")
                resultado["type"] = "postback"
                resultado["text"] = postback.get("title")
            
            # Reacción
            reaction = messaging.get("reaction")
            if reaction:
                resultado["reaction"] = reaction.get("reaction")
                resultado["reaction_message_id"] = reaction.get("mid")
                resultado["type"] = "reaction"
            
            return resultado
            
        except Exception as e:
            print(f"Error parseando webhook Instagram: {e}")
            return None


# Instancia global
_instagram_service: Optional[InstagramService] = None


def get_instagram_service() -> InstagramService:
    """Obtiene instancia del servicio Instagram"""
    global _instagram_service
    if _instagram_service is None:
        _instagram_service = InstagramService()
    return _instagram_service
