"""
================================================================================
                    WEBHOOK WHATSAPP CLOUD API
================================================================================
"""

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from typing import Dict, Any

from config import get_settings
from services.whatsapp import get_whatsapp_service
from services.ai_brain import get_ai_brain
from services.session_manager import get_session_manager
from database.models import CanalMensaje

router = APIRouter(prefix="/webhook/whatsapp", tags=["WhatsApp"])

settings = get_settings()


@router.get("")
async def verificar_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """
    Verificación del webhook de WhatsApp.
    Facebook/Meta envía esta solicitud para verificar el endpoint.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        print(f"Webhook WhatsApp verificado")
        return PlainTextResponse(content=hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verificación fallida")


@router.post("")
async def recibir_mensaje(request: Request):
    """
    Recibe mensajes de WhatsApp.
    """
    try:
        data = await request.json()
        
        # Log para debugging
        print(f"Webhook WhatsApp recibido: {data}")
        
        # Obtener servicios
        wa_service = get_whatsapp_service()
        ai_brain = get_ai_brain()
        session_manager = get_session_manager()
        
        # Parsear mensaje
        mensaje_data = wa_service.parsear_webhook(data)
        
        if not mensaje_data or not mensaje_data.get("text"):
            # No hay mensaje de texto, posiblemente es una notificación de estado
            return {"status": "ok", "message": "No text message"}
        
        telefono = mensaje_data["from"]
        texto = mensaje_data["text"]
        message_id = mensaje_data.get("message_id")
        
        print(f"Mensaje de {telefono}: {texto}")
        
        # Marcar mensaje como leído
        if message_id:
            await wa_service.marcar_leido(message_id)
        
        # Obtener o crear conversación
        session_id = f"wa_{telefono}"
        conversacion = session_manager.obtener_conversacion(
            session_id=session_id,
            canal=CanalMensaje.WHATSAPP,
            user_id=telefono
        )
        
        # Procesar mensaje con IA
        respuesta = await ai_brain.procesar_mensaje(conversacion, texto)
        
        # Extraer preferencias del mensaje
        ai_brain.extraer_preferencias(texto, conversacion)
        
        # Guardar conversación actualizada
        session_manager.guardar_conversacion(conversacion)
        
        # Enviar respuesta de texto
        await wa_service.enviar_mensaje_texto(telefono, respuesta["texto"])
        
        # Si hay productos, enviarlos como lista o imágenes
        if respuesta.get("productos"):
            productos = respuesta["productos"][:3]  # Máximo 3 productos
            
            for producto in productos:
                await wa_service.enviar_producto(telefono, producto)
        
        return {"status": "ok", "message": "Procesado"}
        
    except Exception as e:
        print(f"Error en webhook WhatsApp: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@router.post("/test")
async def test_envio(telefono: str, mensaje: str):
    """
    Endpoint de prueba para enviar mensajes.
    Solo para desarrollo/testing.
    """
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Solo disponible en modo debug")
    
    wa_service = get_whatsapp_service()
    resultado = await wa_service.enviar_mensaje_texto(telefono, mensaje)
    
    return {"status": "enviado", "resultado": resultado}
