"""
================================================================================
                    MCP TOOLBOX SERVICE
                    Integracion con Google GenAI Toolbox
================================================================================
"""

import httpx
from typing import Optional, Dict, Any, List
from functools import lru_cache
import json

from config import get_settings


class MCPToolboxService:
    """Servicio para comunicarse con el MCP Toolbox Server"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:5001"):
        self.base_url = base_url
        self.settings = get_settings()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Obtiene o crea el cliente HTTP"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0
            )
        return self._client
    
    async def close(self):
        """Cierra el cliente HTTP"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def is_available(self) -> bool:
        """Verifica si el servidor MCP esta disponible"""
        try:
            client = await self._get_client()
            response = await client.get("/api/toolset")
            return response.status_code == 200
        except Exception:
            return False
    
    async def get_tools(self, toolset: str = "rosatel_ventas") -> List[Dict]:
        """Obtiene la lista de herramientas disponibles"""
        try:
            client = await self._get_client()
            response = await client.get(f"/api/toolset/{toolset}")
            if response.status_code == 200:
                return response.json().get("tools", [])
            return []
        except Exception as e:
            print(f"Error obteniendo tools: {e}")
            return []
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Llama a una herramienta del toolbox.
        
        Args:
            tool_name: Nombre de la herramienta (ej: buscar_productos)
            parameters: Parametros de la herramienta
            
        Returns:
            Resultado de la herramienta
        """
        try:
            client = await self._get_client()
            
            payload = {
                "tool": tool_name,
                "parameters": parameters
            }
            
            # El endpoint correcto es /api/tool/{nombre}/invoke
            response = await client.post(f"/api/tool/{tool_name}/invoke", json=parameters)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}", "detail": response.text}
                
        except Exception as e:
            print(f"Error llamando tool {tool_name}: {e}")
            return {"error": str(e)}
    
    def _parse_result(self, result: Dict) -> List[Dict]:
        """Parsea el resultado del toolbox que viene como string JSON"""
        try:
            if "error" in result:
                return []
            
            # Intentar varios formatos de respuesta
            result_data = result.get("result") or result.get("rows") or result.get("data") or result
            
            if isinstance(result_data, str):
                parsed = json.loads(result_data)
                return parsed if isinstance(parsed, list) else []
            
            if isinstance(result_data, list):
                return result_data
            
            return []
        except:
            return []
    
    # Metodos de conveniencia para cada herramienta
    
    async def buscar_productos(self, query: str) -> List[Dict]:
        """Busca productos por texto"""
        result = await self.call_tool("buscar_productos", {"query": query})
        return self._parse_result(result)
    
    async def buscar_por_categoria_precio(
        self, 
        categoria: str, 
        precio_min: float, 
        precio_max: float
    ) -> List[Dict]:
        """Busca por categoria y rango de precio"""
        result = await self.call_tool("buscar_por_categoria_precio", {
            "categoria": categoria,
            "precio_min": precio_min,
            "precio_max": precio_max
        })
        return self._parse_result(result)
    
    async def obtener_producto(self, producto_id: str) -> Optional[Dict]:
        """Obtiene un producto por ID"""
        result = await self.call_tool("obtener_producto", {"producto_id": producto_id})
        rows = self._parse_result(result)
        return rows[0] if rows else None
    
    async def buscar_por_color(self, color: str) -> List[Dict]:
        """Busca productos por color"""
        result = await self.call_tool("buscar_por_color", {"color": color})
        return self._parse_result(result)
    
    async def productos_con_descuento(self) -> List[Dict]:
        """Obtiene productos con descuento"""
        result = await self.call_tool("productos_con_descuento", {})
        return self._parse_result(result)
    
    async def productos_economicos(self, limite: int = 5) -> List[Dict]:
        """Obtiene los productos mas economicos"""
        result = await self.call_tool("productos_economicos", {"limite": limite})
        return self._parse_result(result)
    
    async def listar_categorias(self) -> List[Dict]:
        """Lista categorias disponibles"""
        result = await self.call_tool("listar_categorias", {})
        return self._parse_result(result)
    
    async def verificar_stock(self, producto_id: str) -> Optional[Dict]:
        """Verifica stock de un producto"""
        result = await self.call_tool("verificar_stock", {"producto_id": producto_id})
        rows = self._parse_result(result)
        return rows[0] if rows else None
    
    async def busqueda_avanzada(
        self,
        texto: str = "",
        categoria: str = "",
        color: str = "",
        precio_max: float = 99999
    ) -> List[Dict]:
        """Busqueda avanzada con multiples filtros"""
        result = await self.call_tool("busqueda_avanzada", {
            "texto": texto,
            "categoria": categoria,
            "color": color,
            "precio_max": precio_max
        })
        return self._parse_result(result)


# Definicion de herramientas para Gemini Function Calling
GEMINI_TOOLS = [
    {
        "name": "buscar_productos",
        "description": "Busca productos en el inventario de Rosatel por nombre, categoria, tipo, color o descripcion. Usa este tool cuando el usuario busque flores, regalos o productos especificos.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto de busqueda (nombre de producto, categoria, color, etc.)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "buscar_por_categoria_precio",
        "description": "Busca productos filtrando por categoria y rango de precio. Util cuando el usuario menciona un presupuesto especifico.",
        "parameters": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "description": "Categoria del producto (Flores, Peluches, Chocolates, Combos)"
                },
                "precio_min": {
                    "type": "number",
                    "description": "Precio minimo en soles"
                },
                "precio_max": {
                    "type": "number",
                    "description": "Precio maximo en soles"
                }
            },
            "required": ["categoria", "precio_min", "precio_max"]
        }
    },
    {
        "name": "buscar_por_color",
        "description": "Busca productos por color especifico. Util cuando el usuario menciona un color preferido como rojo, rosa, blanco, amarillo.",
        "parameters": {
            "type": "object",
            "properties": {
                "color": {
                    "type": "string",
                    "description": "Color del producto (Rojo, Rosa, Blanco, Amarillo, etc.)"
                }
            },
            "required": ["color"]
        }
    },
    {
        "name": "productos_con_descuento",
        "description": "Obtiene productos que tienen descuento activo. Ideal para mostrar ofertas y promociones al usuario.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "productos_economicos",
        "description": "Lista los productos mas economicos disponibles. Ideal para presupuestos ajustados.",
        "parameters": {
            "type": "object",
            "properties": {
                "limite": {
                    "type": "integer",
                    "description": "Cantidad de productos a mostrar (default 5)"
                }
            }
        }
    },
    {
        "name": "obtener_producto",
        "description": "Obtiene los detalles completos de un producto especifico por su ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "producto_id": {
                    "type": "string",
                    "description": "ID unico del producto"
                }
            },
            "required": ["producto_id"]
        }
    },
    {
        "name": "listar_categorias",
        "description": "Lista todas las categorias de productos disponibles en Rosatel.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]


# Instancia global
_mcp_service: Optional[MCPToolboxService] = None


def get_mcp_service(base_url: str = "http://127.0.0.1:5001") -> MCPToolboxService:
    """Obtiene instancia singleton del servicio MCP"""
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = MCPToolboxService(base_url)
    return _mcp_service
