"""
================================================================================
                         MODELOS DE DATOS
================================================================================
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class CanalMensaje(str, Enum):
    """Canales de comunicación soportados"""
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    WIDGET = "widget"


class Producto(BaseModel):
    """Modelo de producto de Rosatel"""
    id: str = Field(..., alias="ID")
    categoria: str = Field(..., alias="Categoria")
    tipo: str = Field(..., alias="Tipo")
    producto: str = Field(..., alias="Producto")
    foto: Optional[str] = Field(None, alias="Foto")
    color: Optional[str] = Field(None, alias="Color")
    precio: float = Field(..., alias="Precio")
    stock: int = Field(..., alias="Stock")
    descuento: float = Field(0, alias="Descuento")
    precio_final: float = Field(..., alias="Precio_final")
    descripcion: Optional[str] = Field(None, alias="Descripcion")
    
    class Config:
        populate_by_name = True
        
    def to_display_dict(self) -> dict:
        """Convierte a diccionario para mostrar al usuario"""
        return {
            "id": self.id,
            "nombre": self.producto,
            "categoria": self.categoria,
            "tipo": self.tipo,
            "color": self.color,
            "precio_original": f"S/{self.precio:.2f}",
            "precio_final": f"S/{self.precio_final:.2f}",
            "descuento": f"{self.descuento}%" if self.descuento > 0 else None,
            "foto": self.foto,
            "disponible": self.stock > 0
        }
    
    def to_chat_message(self) -> str:
        """Genera mensaje formateado para chat"""
        msg = f"**{self.producto}**\n"
        msg += f"{self.categoria} - {self.tipo}\n"
        
        if self.color:
            msg += f"Color: {self.color}\n"
        
        if self.descuento > 0:
            msg += f"Precio: ~~S/{self.precio:.2f}~~ -> **S/{self.precio_final:.2f}** (-{self.descuento}%)\n"
        else:
            msg += f"Precio: **S/{self.precio_final:.2f}**\n"
        
        if self.stock > 0:
            msg += "Disponible"
        else:
            msg += "Agotado"
        
        return msg


class CarritoItem(BaseModel):
    """Item en el carrito de compras"""
    producto_id: str
    producto_nombre: str
    cantidad: int = 1
    precio_unitario: float
    subtotal: float = 0
    
    def __init__(self, **data):
        super().__init__(**data)
        self.subtotal = self.cantidad * self.precio_unitario


class Carrito(BaseModel):
    """Carrito de compras del usuario"""
    session_id: str
    items: List[CarritoItem] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @property
    def total(self) -> float:
        return sum(item.subtotal for item in self.items)
    
    @property
    def total_items(self) -> int:
        return sum(item.cantidad for item in self.items)
    
    def agregar_item(self, producto: Producto, cantidad: int = 1):
        """Agrega un producto al carrito"""
        # Verificar si ya existe
        for item in self.items:
            if item.producto_id == producto.id:
                item.cantidad += cantidad
                item.subtotal = item.cantidad * item.precio_unitario
                self.updated_at = datetime.now()
                return
        
        # Agregar nuevo item
        nuevo_item = CarritoItem(
            producto_id=producto.id,
            producto_nombre=producto.producto,
            cantidad=cantidad,
            precio_unitario=producto.precio_final
        )
        self.items.append(nuevo_item)
        self.updated_at = datetime.now()
    
    def remover_item(self, producto_id: str):
        """Remueve un producto del carrito"""
        self.items = [item for item in self.items if item.producto_id != producto_id]
        self.updated_at = datetime.now()
    
    def limpiar(self):
        """Vacía el carrito"""
        self.items = []
        self.updated_at = datetime.now()
    
    def to_chat_message(self) -> str:
        """Genera mensaje del carrito para chat"""
        if not self.items:
            return "Tu carrito esta vacio."
        
        msg = "**Tu carrito:**\n\n"
        
        for i, item in enumerate(self.items, 1):
            msg += f"{i}. {item.producto_nombre}\n"
            msg += f"   {item.cantidad} x S/{item.precio_unitario:.2f} = S/{item.subtotal:.2f}\n"
        
        msg += f"\n**Total: S/{self.total:.2f}**"
        
        return msg


class MensajeChat(BaseModel):
    """Mensaje individual en la conversación"""
    role: str  # "user" o "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Optional[dict] = None


class Conversacion(BaseModel):
    """Historial de conversación del usuario"""
    session_id: str
    canal: CanalMensaje
    user_id: Optional[str] = None  # WhatsApp number, Instagram ID, etc.
    mensajes: List[MensajeChat] = []
    carrito: Optional[Carrito] = None
    contexto: dict = {}  # Info adicional: ocasión, presupuesto, preferencias
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    def agregar_mensaje(self, role: str, content: str, metadata: dict = None):
        """Agrega un mensaje a la conversación"""
        mensaje = MensajeChat(
            role=role,
            content=content,
            metadata=metadata
        )
        self.mensajes.append(mensaje)
        self.updated_at = datetime.now()
    
    def get_historial_para_ai(self, limit: int = 20) -> list:
        """Obtiene historial formateado para Gemini"""
        mensajes_recientes = self.mensajes[-limit:]
        return [
            {"role": m.role, "parts": [m.content]}
            for m in mensajes_recientes
        ]
    
    def actualizar_contexto(self, key: str, value):
        """Actualiza información del contexto"""
        self.contexto[key] = value
        self.updated_at = datetime.now()


class DatosEntrega(BaseModel):
    """Datos para el delivery"""
    nombre_receptor: str
    direccion: str
    distrito: str
    ciudad: str = "Lima"
    telefono: str
    fecha_entrega: Optional[str] = None
    horario_preferido: Optional[str] = None
    mensaje_tarjeta: Optional[str] = None
    instrucciones: Optional[str] = None


class Pedido(BaseModel):
    """Modelo de pedido completo"""
    id: Optional[str] = None
    session_id: str
    carrito: Carrito
    datos_entrega: DatosEntrega
    subtotal: float
    costo_envio: float = 15.0
    total: float
    estado: str = "pendiente"  # pendiente, pagado, en_proceso, enviado, entregado
    created_at: datetime = Field(default_factory=datetime.now)
    
    def calcular_total(self):
        self.subtotal = self.carrito.total
        self.total = self.subtotal + self.costo_envio
