"""
================================================================================
                    SERVICIO DE BIGQUERY PARA PRODUCTOS
================================================================================
"""

from typing import List, Optional, Dict, Any
from functools import lru_cache
import json

from database.connection import get_bigquery_client
from database.models import Producto
from config import get_settings
from services.image_utils import convert_drive_url


class BigQueryService:
    """Servicio para consultas de productos en BigQuery"""
    
    def __init__(self):
        self.bq = get_bigquery_client()
        self.settings = get_settings()
        self._table = self.bq.get_table_ref()
        
        # Datos demo para cuando BigQuery no está disponible
        self._demo_products = self._load_demo_products()
    
    def _load_demo_products(self) -> List[dict]:
        """Carga productos demo para modo offline"""
        return [
            {
                "ID": "ROSA-001",
                "Categoria": "Flores",
                "Tipo": "Ramo",
                "Producto": "Ramo de 12 Rosas Rojas",
                "Foto": "https://drive.google.com/uc?export=view&id=demo1",
                "Color": "Rojo",
                "Precio": 89.00,
                "Stock": 50,
                "Descuento": 10,
                "Precio_final": 80.10,
                "Descripcion": "Hermoso ramo de 12 rosas rojas ecuatorianas, envueltas en papel kraft elegante."
            },
            {
                "ID": "ROSA-002",
                "Categoria": "Flores",
                "Tipo": "Sombrerera",
                "Producto": "Sombrerera de Rosas Rosadas",
                "Foto": "https://drive.google.com/uc?export=view&id=demo2",
                "Color": "Rosa",
                "Precio": 149.00,
                "Stock": 30,
                "Descuento": 0,
                "Precio_final": 149.00,
                "Descripcion": "Elegante sombrerera con 24 rosas rosadas premium en caja de lujo."
            },
            {
                "ID": "COMBO-001",
                "Categoria": "Combos",
                "Tipo": "Combo Romántico",
                "Producto": "Combo Amor Eterno",
                "Foto": "https://drive.google.com/uc?export=view&id=demo3",
                "Color": "Rojo",
                "Precio": 199.00,
                "Stock": 20,
                "Descuento": 15,
                "Precio_final": 169.15,
                "Descripcion": "Ramo de 12 rosas + Oso de peluche + Caja de chocolates Ferrero."
            },
            {
                "ID": "GIRA-001",
                "Categoria": "Flores",
                "Tipo": "Ramo",
                "Producto": "Ramo de Girasoles Alegres",
                "Foto": "https://drive.google.com/uc?export=view&id=demo4",
                "Color": "Amarillo",
                "Precio": 79.00,
                "Stock": 40,
                "Descuento": 0,
                "Precio_final": 79.00,
                "Descripcion": "Radiante ramo de 8 girasoles frescos, perfectos para alegrar cualquier día."
            },
            {
                "ID": "PELUCH-001",
                "Categoria": "Peluches",
                "Tipo": "Oso",
                "Producto": "Oso de Peluche Grande",
                "Foto": "https://drive.google.com/uc?export=view&id=demo5",
                "Color": "Beige",
                "Precio": 59.00,
                "Stock": 100,
                "Descuento": 0,
                "Precio_final": 59.00,
                "Descripcion": "Tierno oso de peluche de 40cm, súper suave y abrazable."
            },
            {
                "ID": "CHOCO-001",
                "Categoria": "Chocolates",
                "Tipo": "Caja",
                "Producto": "Caja de Chocolates Premium",
                "Foto": "https://drive.google.com/uc?export=view&id=demo6",
                "Color": "Variado",
                "Precio": 89.00,
                "Stock": 60,
                "Descuento": 5,
                "Precio_final": 84.55,
                "Descripcion": "Exquisita selección de 24 chocolates finos en elegante caja."
            },
            {
                "ID": "TULIP-001",
                "Categoria": "Flores",
                "Tipo": "Ramo",
                "Producto": "Ramo de Tulipanes Holandeses",
                "Foto": "https://drive.google.com/uc?export=view&id=demo7",
                "Color": "Multicolor",
                "Precio": 129.00,
                "Stock": 25,
                "Descuento": 0,
                "Precio_final": 129.00,
                "Descripcion": "Elegante ramo de 15 tulipanes importados en colores surtidos."
            },
            {
                "ID": "ORQUI-001",
                "Categoria": "Flores",
                "Tipo": "Arreglo",
                "Producto": "Orquídea Phalaenopsis",
                "Foto": "https://drive.google.com/uc?export=view&id=demo8",
                "Color": "Blanco",
                "Precio": 169.00,
                "Stock": 15,
                "Descuento": 0,
                "Precio_final": 169.00,
                "Descripcion": "Hermosa orquídea blanca en maceta decorativa, dura semanas."
            }
        ]
    
    def buscar_productos(
        self, 
        query: str = None,
        categoria: str = None,
        tipo: str = None,
        color: str = None,
        precio_min: float = None,
        precio_max: float = None,
        limit: int = 10
    ) -> List[Producto]:
        """
        Busca productos según criterios.
        
        Args:
            query: Texto de búsqueda general
            categoria: Filtrar por categoría
            tipo: Filtrar por tipo
            color: Filtrar por color
            precio_min: Precio mínimo
            precio_max: Precio máximo
            limit: Máximo de resultados
            
        Returns:
            Lista de productos encontrados
        """
        if not self.bq.is_connected:
            return self._buscar_demo(query, categoria, tipo, color, precio_min, precio_max, limit)
        
        # Construir query SQL
        conditions = ["Stock > 0"]
        
        if query:
            query_escaped = query.replace("'", "''")
            conditions.append(f"""
                (LOWER(Producto) LIKE LOWER('%{query_escaped}%')
                OR LOWER(Categoria) LIKE LOWER('%{query_escaped}%')
                OR LOWER(Tipo) LIKE LOWER('%{query_escaped}%')
                OR LOWER(Color) LIKE LOWER('%{query_escaped}%')
                OR LOWER(Descripcion) LIKE LOWER('%{query_escaped}%'))
            """)
        
        if categoria:
            conditions.append(f"LOWER(Categoria) = LOWER('{categoria}')")
        
        if tipo:
            conditions.append(f"LOWER(Tipo) = LOWER('{tipo}')")
        
        if color:
            conditions.append(f"LOWER(Color) LIKE LOWER('%{color}%')")
        
        if precio_min is not None:
            conditions.append(f"Precio_final >= {precio_min}")
        
        if precio_max is not None:
            conditions.append(f"Precio_final <= {precio_max}")
        
        where_clause = " AND ".join(conditions)
        
        sql = f"""
            SELECT * FROM `{self._table}`
            WHERE {where_clause}
            ORDER BY Precio_final ASC
            LIMIT {limit}
        """
        
        results = self.bq.execute_query(sql)
        
        productos = []
        for row in results:
            # Convertir URL de imagen
            if row.get("Foto"):
                row["Foto"] = convert_drive_url(row["Foto"])
            productos.append(Producto(**row))
        
        return productos
    
    def _buscar_demo(
        self, 
        query: str = None,
        categoria: str = None,
        tipo: str = None,
        color: str = None,
        precio_min: float = None,
        precio_max: float = None,
        limit: int = 10
    ) -> List[Producto]:
        """Búsqueda en datos demo"""
        results = []
        
        for p in self._demo_products:
            if p["Stock"] <= 0:
                continue
            
            # Filtrar por query
            if query:
                query_lower = query.lower()
                searchable = f"{p['Producto']} {p['Categoria']} {p['Tipo']} {p['Color']} {p.get('Descripcion', '')}".lower()
                if query_lower not in searchable:
                    continue
            
            # Filtrar por categoría
            if categoria and p["Categoria"].lower() != categoria.lower():
                continue
            
            # Filtrar por tipo
            if tipo and p["Tipo"].lower() != tipo.lower():
                continue
            
            # Filtrar por color
            if color and color.lower() not in p["Color"].lower():
                continue
            
            # Filtrar por precio
            if precio_min is not None and p["Precio_final"] < precio_min:
                continue
            
            if precio_max is not None and p["Precio_final"] > precio_max:
                continue
            
            results.append(Producto(**p))
        
        return results[:limit]
    
    def obtener_producto(self, producto_id: str) -> Optional[Producto]:
        """
        Obtiene un producto por su ID.
        
        Args:
            producto_id: ID del producto
            
        Returns:
            Producto o None si no existe
        """
        if not self.bq.is_connected:
            for p in self._demo_products:
                if p["ID"] == producto_id:
                    return Producto(**p)
            return None
        
        sql = f"""
            SELECT * FROM `{self._table}`
            WHERE ID = '{producto_id}'
            LIMIT 1
        """
        
        results = self.bq.execute_query(sql)
        
        if results:
            row = results[0]
            if row.get("Foto"):
                row["Foto"] = convert_drive_url(row["Foto"])
            return Producto(**row)
        
        return None
    
    def obtener_categorias(self) -> List[str]:
        """Obtiene lista de categorías disponibles"""
        if not self.bq.is_connected:
            return list(set(p["Categoria"] for p in self._demo_products))
        
        sql = f"""
            SELECT DISTINCT Categoria FROM `{self._table}`
            WHERE Stock > 0
            ORDER BY Categoria
        """
        
        results = self.bq.execute_query(sql)
        return [row["Categoria"] for row in results]
    
    def obtener_colores(self) -> List[str]:
        """Obtiene lista de colores disponibles"""
        if not self.bq.is_connected:
            return list(set(p["Color"] for p in self._demo_products if p.get("Color")))
        
        sql = f"""
            SELECT DISTINCT Color FROM `{self._table}`
            WHERE Stock > 0 AND Color IS NOT NULL
            ORDER BY Color
        """
        
        results = self.bq.execute_query(sql)
        return [row["Color"] for row in results]
    
    def obtener_productos_destacados(self, limit: int = 5) -> List[Producto]:
        """Obtiene productos destacados (con descuento o más vendidos)"""
        if not self.bq.is_connected:
            # En demo, retornar los que tienen descuento
            productos = sorted(
                [Producto(**p) for p in self._demo_products if p["Stock"] > 0],
                key=lambda x: x.descuento,
                reverse=True
            )
            return productos[:limit]
        
        sql = f"""
            SELECT * FROM `{self._table}`
            WHERE Stock > 0
            ORDER BY Descuento DESC, Precio_final ASC
            LIMIT {limit}
        """
        
        results = self.bq.execute_query(sql)
        
        productos = []
        for row in results:
            if row.get("Foto"):
                row["Foto"] = convert_drive_url(row["Foto"])
            productos.append(Producto(**row))
        
        return productos
    
    def verificar_stock(self, producto_id: str, cantidad: int = 1) -> bool:
        """Verifica si hay stock suficiente"""
        producto = self.obtener_producto(producto_id)
        if producto:
            return producto.stock >= cantidad
        return False
    
    def obtener_alternativas(self, producto: Producto, limit: int = 3) -> List[Producto]:
        """
        Obtiene productos alternativos similares.
        
        Args:
            producto: Producto base
            limit: Número de alternativas
            
        Returns:
            Lista de productos similares
        """
        return self.buscar_productos(
            categoria=producto.categoria,
            precio_min=producto.precio_final * 0.7,
            precio_max=producto.precio_final * 1.3,
            limit=limit + 1
        )[:limit]


@lru_cache()
def get_bigquery_service() -> BigQueryService:
    """Obtiene instancia singleton del servicio"""
    return BigQueryService()
