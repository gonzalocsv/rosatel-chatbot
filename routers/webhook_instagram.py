"""
================================================================================
                    WEBHOOK INSTAGRAM MESSAGING API
================================================================================
"""

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from typing import Dict, Any

from config import get_settings
from services.instagram import get_instagram_service
from services.ai_brain import get_ai_brain
from services.session_manager import get_session_manager
from database.models import CanalMensaje

router = APIRouter(prefix="/webhook/instagram", tags=["Instagram"])

settings = get_settings()


@router.get("")
async def verificar_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Verificación del webhook de Instagram.
    Facebook/Meta envía esta solicitud para verificar el endpoint.
    """
    # Instagram usa el mismo verify token que WhatsApp en Meta
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        print(f"Webhook Instagram verificado")
        return PlainTextResponse(content=hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verificación fallida")


@router.post("")
async def recibir_mensaje(request: Request):
    """
    Recibe mensajes de Instagram.
    """
    try:
        data = await request.json()
        
        # Log para debugging
        print(f"Webhook Instagram recibido: {data}")
        
        # Verificar que sea de Instagram
        object_type = data.get("object")
        if object_type != "instagram":
            return {"status": "ok", "message": "Not Instagram message"}
        
        # Obtener servicios
        ig_service = get_instagram_service()
        ai_brain = get_ai_brain()
        session_manager = get_session_manager()
        
        # Parsear mensaje
        mensaje_data = ig_service.parsear_webhook(data)
        
        if not mensaje_data:
            return {"status": "ok", "message": "No message data"}
        
        # Ignorar reacciones y otros tipos no procesables
        if mensaje_data.get("type") == "reaction":
            return {"status": "ok", "message": "Reaction ignored"}
        
        sender_id = mensaje_data["sender_id"]
        texto = mensaje_data.get("text")
        
        if not texto:
            return {"status": "ok", "message": "No text message"}
        
        print(f"Mensaje de {sender_id}: {texto}")
        
        # Marcar como visto y mostrar escribiendo
        await ig_service.marcar_visto(sender_id)
        await ig_service.mostrar_escribiendo(sender_id)
        
        # Obtener o crear conversación
        session_id = f"ig_{sender_id}"
        conversacion = session_manager.obtener_conversacion(
            session_id=session_id,
            canal=CanalMensaje.INSTAGRAM,
            user_id=sender_id
        )
        
        # Manejar postbacks (botones)
        if mensaje_data.get("type") == "postback":
            payload = mensaje_data.get("postback_payload", "")
            
            if payload.startswith("VER_PRODUCTO_"):
                producto_id = payload.replace("VER_PRODUCTO_", "")
                texto = f"Quiero ver el producto {producto_id}"
            
            elif payload.startswith("COMPRAR_"):
                producto_id = payload.replace("COMPRAR_", "")
                texto = f"Quiero comprar el producto {producto_id}"
        
        # Procesar mensaje con IA
        respuesta = await ai_brain.procesar_mensaje(conversacion, texto)
        
        # Extraer preferencias
        ai_brain.extraer_preferencias(texto, conversacion)
        
        # Guardar conversación
        session_manager.guardar_conversacion(conversacion)
        
        # Enviar respuesta de texto
        await ig_service.enviar_mensaje_texto(sender_id, respuesta["texto"])
        
        # Si hay productos, enviarlos como carrusel
        if respuesta.get("productos") and len(respuesta["productos"]) > 1:
            await ig_service.enviar_carrusel_productos(sender_id, respuesta["productos"][:5])
        elif respuesta.get("productos"):
            # Un solo producto
            await ig_service.enviar_producto(sender_id, respuesta["productos"][0])
        
        return {"status": "ok", "message": "Procesado"}
        
    except Exception as e:
        print(f"Error en webhook Instagram: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.post("/test")
async def test_envio(recipient_id: str, mensaje: str):
    """
    Endpoint de prueba para enviar mensajes.
    Solo para desarrollo/testing.
    """
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Solo disponible en modo debug")
    
    ig_service = get_instagram_service()
    resultado = await ig_service.enviar_mensaje_texto(recipient_id, mensaje)
    
    return {"status": "enviado", "resultado": resultado}
