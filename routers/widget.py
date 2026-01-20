"""
================================================================================
                    API PARA WIDGET WEB
================================================================================
"""

from fastapi import APIRouter, Request, HTTPException, Header, Query, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
import uuid
import secrets
import os

from config import get_settings, WELCOME_MESSAGE

security = HTTPBasic()
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "vendechatiando")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verifica credenciales de acceso"""
    correct_password = secrets.compare_digest(credentials.password, DEMO_PASSWORD)
    if not correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True
from services.ai_brain import get_ai_brain
from services.session_manager import get_session_manager
from services.bigquery_service import get_bigquery_service
from database.models import CanalMensaje, Producto

router = APIRouter(prefix="/widget", tags=["Widget"])

settings = get_settings()
templates = Jinja2Templates(directory="templates")


class MensajeRequest(BaseModel):
    """Request para enviar mensaje"""
    session_id: str
    mensaje: str


class MensajeResponse(BaseModel):
    """Response con mensaje del bot"""
    texto: str
    burbujas: Optional[List[str]] = None
    productos: Optional[List[dict]] = None
    carrito: Optional[dict] = None


class IniciarChatRequest(BaseModel):
    """Request para iniciar chat"""
    session_id: Optional[str] = None


class IniciarChatResponse(BaseModel):
    """Response al iniciar chat"""
    session_id: str
    mensaje_bienvenida: str


def verificar_api_key(x_api_key: str = Header(None)):
    """Verifica la API key del widget"""
    if not x_api_key or x_api_key != settings.widget_api_key:
        raise HTTPException(status_code=401, detail="API key inválida")
    return True


@router.get("/embed", response_class=HTMLResponse)
async def obtener_widget(request: Request, authenticated: bool = Depends(verify_credentials)):
    """
    Retorna el HTML del widget embebible (protegido con password).
    """
    return templates.TemplateResponse(
        "widget.html",
        {
            "request": request,
            "bot_name": settings.bot_name,
            "company_name": settings.company_name,
            "primary_color": settings.primary_color,
            "api_key": settings.widget_api_key
        }
    )


@router.post("/chat/iniciar", response_model=IniciarChatResponse)
async def iniciar_chat(
    request: IniciarChatRequest,
    x_api_key: str = Header(None)
):
    """
    Inicia una nueva sesión de chat.
    """
    verificar_api_key(x_api_key)
    
    # Generar o usar session_id existente
    session_id = request.session_id or f"widget_{uuid.uuid4().hex[:12]}"
    
    # Crear conversación
    session_manager = get_session_manager()
    conversacion = session_manager.obtener_conversacion(
        session_id=session_id,
        canal=CanalMensaje.WIDGET
    )
    
    # Agregar mensaje de bienvenida si es nueva
    if len(conversacion.mensajes) == 0:
        conversacion.agregar_mensaje("assistant", WELCOME_MESSAGE)
        session_manager.guardar_conversacion(conversacion)
    
    return IniciarChatResponse(
        session_id=session_id,
        mensaje_bienvenida=WELCOME_MESSAGE
    )


@router.post("/chat/mensaje", response_model=MensajeResponse)
async def enviar_mensaje(
    request: MensajeRequest,
    x_api_key: str = Header(None)
):
    """
    Envía un mensaje y recibe respuesta del bot.
    """
    verificar_api_key(x_api_key)
    
    if not request.mensaje or not request.mensaje.strip():
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    
    # Obtener servicios
    session_manager = get_session_manager()
    ai_brain = get_ai_brain()
    
    # Obtener conversación
    conversacion = session_manager.obtener_conversacion(
        session_id=request.session_id,
        canal=CanalMensaje.WIDGET
    )
    
    # Procesar mensaje
    respuesta = await ai_brain.procesar_mensaje(conversacion, request.mensaje.strip())
    
    # Extraer preferencias
    ai_brain.extraer_preferencias(request.mensaje, conversacion)
    
    # Guardar conversación
    session_manager.guardar_conversacion(conversacion)
    
    # Preparar respuesta
    productos_data = None
    if respuesta.get("productos"):
        # Los productos ya vienen como dict del ai_brain
        productos_data = respuesta["productos"] if isinstance(respuesta["productos"], list) else []
    
    carrito_data = None
    if conversacion.carrito and conversacion.carrito.items:
        carrito_data = {
            "items": [
                {
                    "id": item.producto_id,
                    "nombre": item.producto_nombre,
                    "cantidad": item.cantidad,
                    "precio": item.precio_unitario,
                    "subtotal": item.subtotal
                }
                for item in conversacion.carrito.items
            ],
            "total": conversacion.carrito.total
        }
    
    # Obtener burbujas o usar texto simple
    burbujas = respuesta.get("burbujas", [respuesta["texto"]] if isinstance(respuesta["texto"], str) else respuesta["texto"])
    texto_principal = burbujas[0] if burbujas else respuesta["texto"]
    
    return MensajeResponse(
        texto=texto_principal,
        burbujas=burbujas,
        productos=productos_data,
        carrito=carrito_data
    )


@router.get("/productos/buscar")
async def buscar_productos(
    q: str = Query(..., min_length=2),
    categoria: Optional[str] = None,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    limit: int = Query(10, le=20),
    x_api_key: str = Header(None)
):
    """
    Busca productos directamente.
    """
    verificar_api_key(x_api_key)
    
    bq_service = get_bigquery_service()
    productos = bq_service.buscar_productos(
        query=q,
        categoria=categoria,
        precio_min=precio_min,
        precio_max=precio_max,
        limit=limit
    )
    
    return {
        "productos": [p.to_display_dict() for p in productos],
        "total": len(productos)
    }


@router.get("/productos/{producto_id}")
async def obtener_producto(
    producto_id: str,
    x_api_key: str = Header(None)
):
    """
    Obtiene detalles de un producto.
    """
    verificar_api_key(x_api_key)
    
    bq_service = get_bigquery_service()
    producto = bq_service.obtener_producto(producto_id)
    
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    return producto.to_display_dict()


@router.get("/productos/destacados")
async def obtener_destacados(
    limit: int = Query(5, le=10),
    x_api_key: str = Header(None)
):
    """
    Obtiene productos destacados.
    """
    verificar_api_key(x_api_key)
    
    bq_service = get_bigquery_service()
    productos = bq_service.obtener_productos_destacados(limit)
    
    return {
        "productos": [p.to_display_dict() for p in productos]
    }


@router.get("/categorias")
async def obtener_categorias(x_api_key: str = Header(None)):
    """
    Obtiene lista de categorías disponibles.
    """
    verificar_api_key(x_api_key)
    
    bq_service = get_bigquery_service()
    categorias = bq_service.obtener_categorias()
    
    return {"categorias": categorias}


@router.post("/chat/carrito/agregar")
async def agregar_al_carrito(
    session_id: str,
    producto_id: str,
    cantidad: int = 1,
    x_api_key: str = Header(None)
):
    """
    Agrega un producto al carrito.
    """
    verificar_api_key(x_api_key)
    
    session_manager = get_session_manager()
    bq_service = get_bigquery_service()
    
    # Obtener producto
    producto = bq_service.obtener_producto(producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    
    if producto.stock < cantidad:
        raise HTTPException(status_code=400, detail="Stock insuficiente")
    
    # Obtener conversación
    conversacion = session_manager.obtener_conversacion(
        session_id=session_id,
        canal=CanalMensaje.WIDGET
    )
    
    # Agregar al carrito
    conversacion.carrito.agregar_item(producto, cantidad)
    session_manager.guardar_conversacion(conversacion)
    
    return {
        "mensaje": f"{producto.producto} agregado al carrito",
        "carrito": {
            "items": len(conversacion.carrito.items),
            "total": conversacion.carrito.total
        }
    }


@router.get("/chat/carrito")
async def ver_carrito(
    session_id: str,
    x_api_key: str = Header(None)
):
    """
    Obtiene el carrito actual.
    """
    verificar_api_key(x_api_key)
    
    session_manager = get_session_manager()
    conversacion = session_manager.obtener_conversacion(
        session_id=session_id,
        canal=CanalMensaje.WIDGET
    )
    
    if not conversacion.carrito or not conversacion.carrito.items:
        return {"items": [], "total": 0}
    
    return {
        "items": [
            {
                "id": item.producto_id,
                "nombre": item.producto_nombre,
                "cantidad": item.cantidad,
                "precio": item.precio_unitario,
                "subtotal": item.subtotal
            }
            for item in conversacion.carrito.items
        ],
        "total": conversacion.carrito.total
    }


@router.get("/health")
async def health_check():
    """
    Verifica el estado del servicio.
    """
    session_manager = get_session_manager()
    bq_service = get_bigquery_service()
    
    return {
        "status": "ok",
        "bot_name": settings.bot_name,
        "redis_connected": session_manager.is_connected,
        "bigquery_connected": bq_service.bq.is_connected,
        "sesiones_activas": session_manager.obtener_estadisticas()["sesiones_activas"]
    }
