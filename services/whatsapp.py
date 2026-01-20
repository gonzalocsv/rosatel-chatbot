"""
================================================================================
                    SERVICIO WHATSAPP CLOUD API
================================================================================
"""

import httpx
from typing import Optional, Dict, Any, List
from config import get_settings
from database.models import Producto
from services.image_utils import convert_drive_url


class WhatsAppService:
    """Servicio para WhatsApp Cloud API"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.settings = get_settings()
        self.token = self.settings.whatsapp_token
        self.phone_number_id = self.settings.whatsapp_phone_number_id
    
    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    @property
    def messages_url(self) -> str:
        return f"{self.BASE_URL}/{self.phone_number_id}/messages"
    
    async def enviar_mensaje_texto(
        self, 
        telefono: str, 
        mensaje: str
    ) -> Dict[str, Any]:
        """
        Envía un mensaje de texto simple.
        
        Args:
            telefono: Número de teléfono (con código de país)
            mensaje: Texto del mensaje
            
        Returns:
            Respuesta de la API
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": mensaje
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_imagen(
        self, 
        telefono: str, 
        imagen_url: str,
        caption: str = None
    ) -> Dict[str, Any]:
        """
        Envía una imagen.
        
        Args:
            telefono: Número de teléfono
            imagen_url: URL de la imagen
            caption: Texto opcional debajo de la imagen
        """
        # Convertir URL de Drive si es necesario
        imagen_url = convert_drive_url(imagen_url) or imagen_url
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "image",
            "image": {
                "link": imagen_url
            }
        }
        
        if caption:
            payload["image"]["caption"] = caption
        
        return await self._send_request(payload)
    
    async def enviar_producto(
        self, 
        telefono: str, 
        producto: Producto
    ) -> Dict[str, Any]:
        """
        Envía información de un producto con imagen.
        
        Args:
            telefono: Número de teléfono
            producto: Objeto Producto
        """
        # Construir caption
        caption = f"*{producto.producto}*\n"
        caption += f"{producto.categoria} - {producto.tipo}\n"
        
        if producto.color:
            caption += f"Color: {producto.color}\n"
        
        if producto.descuento > 0:
            caption += f"~S/{producto.precio:.2f}~ -> *S/{producto.precio_final:.2f}* (-{producto.descuento}%)\n"
        else:
            caption += f"*S/{producto.precio_final:.2f}*\n"
        
        caption += "\nDisponible para envio" if producto.stock > 0 else "\nAgotado"
        
        if producto.foto:
            return await self.enviar_imagen(telefono, producto.foto, caption)
        else:
            return await self.enviar_mensaje_texto(telefono, caption)
    
    async def enviar_lista_productos(
        self, 
        telefono: str, 
        productos: List[Producto],
        titulo: str = "Productos disponibles"
    ) -> Dict[str, Any]:
        """
        Envía una lista interactiva de productos.
        
        Args:
            telefono: Número de teléfono
            productos: Lista de productos
            titulo: Título de la lista
        """
        # Construir secciones
        rows = []
        for p in productos[:10]:  # WhatsApp limita a 10 items
            rows.append({
                "id": p.id,
                "title": p.producto[:24],  # Max 24 chars
                "description": f"S/{p.precio_final:.2f} - {p.categoria}"[:72]  # Max 72 chars
            })
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": titulo
                },
                "body": {
                    "text": "Selecciona un producto para ver más detalles:"
                },
                "footer": {
                    "text": "Rosatel"
                },
                "action": {
                    "button": "Ver productos",
                    "sections": [
                        {
                            "title": "Productos",
                            "rows": rows
                        }
                    ]
                }
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_botones(
        self, 
        telefono: str, 
        mensaje: str,
        botones: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Envía mensaje con botones de respuesta rápida.
        
        Args:
            telefono: Número de teléfono
            mensaje: Texto del mensaje
            botones: Lista de botones [{"id": "btn1", "title": "Opción 1"}, ...]
        """
        buttons = []
        for btn in botones[:3]:  # Max 3 botones
            buttons.append({
                "type": "reply",
                "reply": {
                    "id": btn["id"],
                    "title": btn["title"][:20]  # Max 20 chars
                }
            })
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": mensaje
                },
                "action": {
                    "buttons": buttons
                }
            }
        }
        
        return await self._send_request(payload)
    
    async def enviar_template(
        self, 
        telefono: str,
        template_name: str,
        language: str = "es",
        components: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Envía un mensaje de plantilla.
        
        Args:
            telefono: Número de teléfono
            template_name: Nombre de la plantilla
            language: Código de idioma
            components: Componentes de la plantilla
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": telefono,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language
                }
            }
        }
        
        if components:
            payload["template"]["components"] = components
        
        return await self._send_request(payload)
    
    async def marcar_leido(self, message_id: str) -> Dict[str, Any]:
        """Marca un mensaje como leído"""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        return await self._send_request(payload)
    
    async def _send_request(self, payload: dict) -> Dict[str, Any]:
        """Envía request a la API de WhatsApp"""
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
            print(f"Error HTTP WhatsApp: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
            return {"error": str(e), "status_code": e.response.status_code}
            
        except Exception as e:
            print(f"Error WhatsApp: {e}")
            return {"error": str(e)}
    
    def parsear_webhook(self, data: dict) -> Optional[Dict[str, Any]]:
        """
        Parsea datos del webhook de WhatsApp.
        
        Args:
            data: Datos del webhook
            
        Returns:
            Dict con mensaje parseado o None
        """
        try:
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            
            # Verificar si hay mensajes
            messages = value.get("messages", [])
            if not messages:
                return None
            
            message = messages[0]
            contact = value.get("contacts", [{}])[0]
            
            resultado = {
                "message_id": message.get("id"),
                "from": message.get("from"),
                "timestamp": message.get("timestamp"),
                "type": message.get("type"),
                "contact_name": contact.get("profile", {}).get("name"),
                "wa_id": contact.get("wa_id")
            }
            
            # Parsear según tipo de mensaje
            msg_type = message.get("type")
            
            if msg_type == "text":
                resultado["text"] = message.get("text", {}).get("body")
                
            elif msg_type == "interactive":
                interactive = message.get("interactive", {})
                inter_type = interactive.get("type")
                
                if inter_type == "button_reply":
                    resultado["button_id"] = interactive.get("button_reply", {}).get("id")
                    resultado["button_title"] = interactive.get("button_reply", {}).get("title")
                    resultado["text"] = resultado["button_title"]
                    
                elif inter_type == "list_reply":
                    resultado["list_id"] = interactive.get("list_reply", {}).get("id")
                    resultado["list_title"] = interactive.get("list_reply", {}).get("title")
                    resultado["text"] = resultado["list_title"]
                    
            elif msg_type == "image":
                resultado["image_id"] = message.get("image", {}).get("id")
                resultado["image_caption"] = message.get("image", {}).get("caption")
                resultado["text"] = resultado.get("image_caption", "[Imagen recibida]")
                
            elif msg_type == "location":
                location = message.get("location", {})
                resultado["latitude"] = location.get("latitude")
                resultado["longitude"] = location.get("longitude")
                resultado["text"] = f"Ubicacion: {location.get('latitude')}, {location.get('longitude')}"
            
            return resultado
            
        except Exception as e:
            print(f"Error parseando webhook WhatsApp: {e}")
            return None


# Instancia global
_whatsapp_service: Optional[WhatsAppService] = None


def get_whatsapp_service() -> WhatsAppService:
    """Obtiene instancia del servicio WhatsApp"""
    global _whatsapp_service
    if _whatsapp_service is None:
        _whatsapp_service = WhatsAppService()
    return _whatsapp_service
