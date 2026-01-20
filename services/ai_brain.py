"""
================================================================================
                    CEREBRO IA - GEMINI + MCP TOOLBOX
================================================================================
"""

import google.generativeai as genai
from typing import Optional, List, Dict, Any, Tuple
import re
import json
from functools import lru_cache
from datetime import datetime
import pytz

from config import get_settings, SYSTEM_PROMPT, TIENDAS_ROSATEL
from database.models import Conversacion, Carrito, Producto, CanalMensaje
from services.bigquery_service import get_bigquery_service
from services.mcp_toolbox import get_mcp_service

# Timezone de Lima
LIMA_TZ = pytz.timezone('America/Lima')


class AIBrain:
    """Cerebro de IA usando Google Gemini"""
    
    def __init__(self):
        self.settings = get_settings()
        self.bq_service = get_bigquery_service()
        self.mcp_service = get_mcp_service()
        self._configure_gemini()
        
        # Patrones para detectar acciones especiales
        self.action_patterns = {
            "BUSCAR_PRODUCTO": r'\[BUSCAR_PRODUCTO:([^\]]+)\]',
            "MOSTRAR_PRODUCTO": r'\[MOSTRAR_PRODUCTO:([^\]]+)\]',
            "PRODUCTO": r'\[PRODUCTO:([^\]]+)\]',  # Nuevo formato: [PRODUCTO:id|nombre|precio|url]
            "AGREGAR_CARRITO": r'\[AGREGAR_CARRITO:([^\]]+)\]',
            "CHECKOUT": r'\[CHECKOUT:([^\]]+)\]',  # Nuevo formato: [CHECKOUT:codigo]
            "VER_CARRITO": r'\[VER_CARRITO\]',
            "GENERAR_CHECKOUT": r'\[GENERAR_CHECKOUT\]'
        }
    
    def _convertir_drive_url(self, url: str) -> str:
        """Convierte URL de Google Drive a URL directa de imagen (formato thumbnail)"""
        if not url:
            return ""
        
        # Patron: /file/d/{ID}/ o /d/{ID}/
        match = re.search(r'/(?:file/)?d/([a-zA-Z0-9_-]+)', url)
        if match:
            file_id = match.group(1)
            # Usar formato lh3 que es más confiable para imágenes
            return f"https://lh3.googleusercontent.com/d/{file_id}=w300"
        
        # Patron: ?id={ID}
        match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
        if match:
            file_id = match.group(1)
            return f"https://lh3.googleusercontent.com/d/{file_id}=w300"
        
        return url
    
    def _generar_codigo_carrito(self) -> str:
        """Genera codigo random para checkout"""
        import random
        import string
        return "RST" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    def _configure_gemini(self):
        """Configura la API de Gemini"""
        if self.settings.gemini_api_key:
            genai.configure(api_key=self.settings.gemini_api_key)
            
            # Configuracion de generacion
            self.generation_config = genai.GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=1024,
            )
            
            # Configuracion de seguridad
            self.safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            ]
            
            # Inicializar modelo
            self.model = genai.GenerativeModel(
                model_name=self.settings.gemini_model,
                generation_config=self.generation_config,
                safety_settings=self.safety_settings
            )
            
            print(f"Gemini configurado: {self.settings.gemini_model}")
        else:
            self.model = None
            print("Gemini API key no configurada - usando modo demo")
    
    async def procesar_mensaje(
        self, 
        conversacion: Conversacion,
        mensaje_usuario: str
    ) -> Dict[str, Any]:
        """Procesa un mensaje del usuario y genera respuesta."""
        # PRIMERO extraer preferencias del mensaje para actualizar contexto
        self.extraer_preferencias(mensaje_usuario, conversacion)
        
        # =====================================================
        # DETECTAR RESPUESTA AFIRMATIVA A UPSELLING
        # =====================================================
        respuesta_upsell = await self._detectar_upselling_response(mensaje_usuario, conversacion)
        if respuesta_upsell:
            conversacion.agregar_mensaje("user", mensaje_usuario)
            conversacion.agregar_mensaje("assistant", respuesta_upsell["texto_limpio"])
            return respuesta_upsell
        
        # Agregar mensaje del usuario al historial
        conversacion.agregar_mensaje("user", mensaje_usuario)
        
        # Generar respuesta con IA (ahora con contexto actualizado)
        respuesta_raw = await self._generar_respuesta(conversacion, mensaje_usuario)
        
        # Procesar acciones especiales en la respuesta
        respuesta_procesada, productos, acciones = await self._procesar_acciones(
            respuesta_raw, 
            conversacion
        )
        
        # =====================================================
        # AGREGAR PRODUCTO DE UPSELLING como tarjeta al FINAL
        # =====================================================
        upsell_prod = conversacion.contexto.get("upsell_producto")
        if productos and upsell_prod:
            upsell = conversacion.contexto.pop("upsell_producto")
            upsell["es_upsell"] = True
            
            # Remover si ya está en la lista (evitar duplicados)
            productos = [p for p in productos if str(p.get("id", "")) != str(upsell.get("id", ""))]
            
            # Agregar al final
            productos.append(upsell)
        
        # =====================================================
        # FALLBACK: Si no hay productos pero debería haberlos
        # PERO NO si el usuario preguntó por algo específico nuevo
        # =====================================================
        if not productos:
            # Detectar si el usuario pide algo NUEVO (diferente al contexto)
            nueva_solicitud = self._detectar_nueva_solicitud(mensaje_usuario)
            if nueva_solicitud:
                # Buscar lo que el usuario pidió directamente
                productos = await self._buscar_por_solicitud(nueva_solicitud, conversacion)
            else:
                # Solo usar fallback si NO acabamos de agregar al carrito y NO es "finalizar"
                resp_lower = respuesta_procesada.lower()
                msg_lower = mensaje_usuario.lower()
                
                # NO activar fallback si: agregamos al carrito, finalizamos, o usuario mencionó carrito
                skip_fallback = (
                    "agregado" in resp_lower or 
                    "finaliza" in resp_lower or 
                    "carrito" in msg_lower or
                    "lo quiero" in msg_lower
                )
                
                if not skip_fallback:
                    productos = await self._buscar_productos_fallback(conversacion)
        
        # Dividir en burbujas si es necesario
        burbujas = [b.strip() for b in respuesta_procesada.split("|NUEVA_BURBUJA|") if b.strip()]
        
        # Agregar respuesta al historial (sin separadores)
        respuesta_historial = " ".join(burbujas)
        conversacion.agregar_mensaje("assistant", respuesta_historial)
        
        return {
            "texto": burbujas[0] if len(burbujas) == 1 else burbujas,
            "burbujas": burbujas,
            "productos": productos,
            "acciones": acciones,
            "carrito": conversacion.carrito
        }
    
    def _detectar_nueva_solicitud(self, mensaje: str) -> Optional[str]:
        """Detecta si el usuario pide algo específico nuevo."""
        mensaje_lower = mensaje.lower()
        
        # Si es agregar al carrito, NO es nueva solicitud
        if "carrito" in mensaje_lower or "agregar" in mensaje_lower:
            return None
        
        # Patrones de nueva solicitud
        solicitudes = {
            "chocolate": ["chocolate", "chocolates", "ferrero", "iberica", "bombones"],
            "peluche": ["peluche", "peluches", "oso", "osito"],  # Quitado "hugo" porque puede ser nombre de producto
            "globo": ["globo", "globos"],
            "vino": ["vino", "vinos", "licor", "champagne", "espumante"],
            "flores": ["flor", "flores", "rosas", "tulipanes", "girasoles"],
            "ramo": ["ramo", "ramos", "bouquet"],
        }
        
        # Detectar pregunta directa: "tienes X?", "hay X?", "busco X"
        for categoria, keywords in solicitudes.items():
            for kw in keywords:
                if kw in mensaje_lower:
                    # Verificar que es una solicitud de búsqueda
                    if any(p in mensaje_lower for p in ["tienes", "tienen", "hay", "busco", "necesito", "muestrame", "ver ", "dame"]):
                        return categoria
        
        return None
    
    async def _buscar_por_solicitud(self, tipo: str, conversacion: Conversacion = None) -> List[dict]:
        """Busca productos por tipo específico solicitado."""
        try:
            productos_raw = await self.mcp_service.buscar_productos(tipo)
            if not productos_raw:
                return []
            
            # Obtener ID del último upselling para no mostrarlo de nuevo si ya se mostró
            ultimo_upsell_id = ""
            if conversacion and conversacion.contexto:
                ultimo_upsell_id = str(conversacion.contexto.get("ultimo_upsell_id", ""))
            
            productos = []
            for p in productos_raw[:5]:
                if not isinstance(p, dict):
                    continue
                prod_id = p.get("ID", "")
                # Saltar si es el producto que ya se mostró como upselling
                if str(prod_id) == ultimo_upsell_id:
                    continue
                productos.append({
                    "id": prod_id,
                    "nombre": p.get("Producto", "").strip(),
                    "precio": f"S/{p.get('Precio_final', '')}",
                    "precio_num": float(str(p.get("Precio_final", "0")).replace(",", "")),
                    "imagen": self._convertir_drive_url(p.get("Foto", "")),
                    "categoria": p.get("Categoria", ""),
                    "tipo": p.get("Tipo", "")
                })
            return productos
        except Exception as e:
            print(f"[Error buscando por solicitud] {e}")
            return []
    
    async def _buscar_productos_fallback(self, conversacion: Conversacion) -> List[dict]:
        """Busca productos si hay contexto suficiente pero Gemini no los incluyó"""
        contexto = conversacion.contexto or {}
        
        # Verificar si tenemos suficiente contexto
        tiene_ocasion = "ocasion" in contexto
        tiene_tipo = "tipo_producto" in contexto
        tiene_presupuesto = "presupuesto_max" in contexto
        tiene_preferencia = "color_preferido" in contexto or "flor_preferida" in contexto
        
        
        # Solo buscar si hay presupuesto + (ocasion O tipo O preferencia)
        if not tiene_presupuesto:
            return []
        if not (tiene_ocasion or tiene_tipo or tiene_preferencia):
            return []
        
        # Construir query
        query_parts = []
        if "tipo_producto" in contexto:
            query_parts.append(contexto["tipo_producto"])
        if "flor_preferida" in contexto:
            query_parts.append(contexto["flor_preferida"])
        if "ocasion" in contexto:
            query_parts.append(contexto["ocasion"])
        if "color_preferido" in contexto:
            query_parts.append(contexto["color_preferido"])
        
        query = " ".join(query_parts) if query_parts else "flores"
        presupuesto = float(contexto.get("presupuesto_max", 500))
        
        
        try:
            productos_raw = await self.mcp_service.buscar_productos(query)
            
            # Si no hay suficientes resultados, buscar alternativas
            if not productos_raw or len(productos_raw) < 3:
                alternativas = []
                
                # Buscar solo por tipo de producto (ej: "Peluche" sin categoría)
                if "tipo_producto" in contexto:
                    alt = await self.mcp_service.buscar_productos(contexto["tipo_producto"])
                    if alt:
                        alternativas.extend(alt)
                
                # Buscar por flor
                if "flor_preferida" in contexto:
                    alt = await self.mcp_service.buscar_productos(contexto["flor_preferida"])
                    if alt:
                        alternativas.extend(alt)
                
                # Buscar solo por ocasión
                if "ocasion" in contexto:
                    alt = await self.mcp_service.buscar_productos(contexto["ocasion"])
                    if alt:
                        alternativas.extend(alt)
                
                # Combinar sin duplicados
                ids_vistos = set(p.get("ID") for p in (productos_raw or []) if isinstance(p, dict))
                for alt in alternativas:
                    if isinstance(alt, dict) and alt.get("ID") not in ids_vistos:
                        productos_raw = productos_raw or []
                        productos_raw.append(alt)
                        ids_vistos.add(alt.get("ID"))
            
            if not productos_raw:
                productos_raw = await self.mcp_service.productos_economicos(5)
            
            # Filtrar y ordenar productos
            productos_con_precio = []
            
            for p in productos_raw:
                if not isinstance(p, dict):
                    continue
                try:
                    precio = float(str(p.get("Precio_final", "0")).replace(",", ""))
                    imagen = self._convertir_drive_url(p.get("Foto", ""))
                    productos_con_precio.append({
                        "id": p.get("ID", ""),
                        "nombre": p.get("Producto", "").strip(),
                        "precio": f"S/{precio:.0f}",
                        "precio_num": precio,
                        "imagen": imagen,
                        "categoria": p.get("Categoria", ""),
                        "tipo": p.get("Tipo", ""),
                        "en_presupuesto": precio <= presupuesto * 1.2
                    })
                except:
                    pass
            
            # Ordenar: primero los que están en presupuesto, luego por precio
            productos_con_precio.sort(key=lambda x: (not x["en_presupuesto"], x["precio_num"]))
            
            # Tomar los 3 mejores
            return productos_con_precio[:3]
            
        except Exception as e:
            print(f"[ERROR fallback] {e}")
            return []
    
    async def _generar_respuesta(
        self, 
        conversacion: Conversacion,
        mensaje_usuario: str
    ) -> str:
        """Genera respuesta usando Gemini"""
        
        if not self.model:
            return await self._respuesta_demo(mensaje_usuario, conversacion)
        
        try:
            # Construir contexto
            contexto_adicional = self._construir_contexto(conversacion)
            
            # Buscar productos proactivamente si el mensaje lo sugiere
            productos_context = await self._buscar_productos_proactivo(mensaje_usuario, conversacion)
            
            # Obtener hora actual de Lima
            from datetime import datetime
            import pytz
            try:
                lima_tz = pytz.timezone('America/Lima')
                hora_lima = datetime.now(lima_tz)
                hora_actual = hora_lima.strftime("%H:%M")
                hora_int = hora_lima.hour
                
                if hora_int >= 22 or hora_int < 8:
                    estado_tiendas = f"HORA ACTUAL: {hora_actual} - Las tiendas fisicas estan CERRADAS (abren 8AM-10PM). Solo tienda online disponible."
                elif hora_int < 10:
                    estado_tiendas = f"HORA ACTUAL: {hora_actual} - Solo Surco y Surco Centro estan abiertas. La Fontana abre a las 10AM."
                else:
                    estado_tiendas = f"HORA ACTUAL: {hora_actual} - Todas las tiendas estan ABIERTAS."
            except:
                estado_tiendas = ""
            
            # Prompt completo
            prompt = f"""
{SYSTEM_PROMPT}

{estado_tiendas}

{contexto_adicional}

{productos_context}

HISTORIAL:
{self._formatear_historial(conversacion)}

USUARIO: {mensaje_usuario}

ROSA:"""
            
            # Generar respuesta
            response = self.model.generate_content(prompt)
            
            if response.text:
                return response.text.strip()
            else:
                return "Lo siento, no pude procesar tu mensaje. Podrias repetirlo?"
                
        except Exception as e:
            print(f"Error en Gemini: {e}")
            import traceback
            traceback.print_exc()
            return await self._respuesta_demo(mensaje_usuario, conversacion)
    
    async def _detectar_upselling_response(
        self,
        mensaje: str,
        conversacion: Conversacion
    ) -> Optional[Dict[str, Any]]:
        """Detecta si el usuario está respondiendo afirmativamente a una sugerencia de upselling."""
        mensaje_lower = mensaje.lower().strip()
        
        # Si el mensaje menciona "agregar al carrito", no es respuesta a upselling
        if "carrito" in mensaje_lower or "agregar" in mensaje_lower:
            return None
        
        # Palabras afirmativas simples (sin "quiero" que puede ser "quiero agregar X")
        afirmaciones = ["si", "sí", "ok", "dale", "claro", "por supuesto", "me interesa", 
                       "perfecto", "bueno", "va", "muestrame", "mostrame"]
        
        es_afirmativo = any(mensaje_lower.startswith(afirm) or mensaje_lower == afirm for afirm in afirmaciones)
        
        if not es_afirmativo:
            return None
        
        # Buscar en los últimos mensajes del bot para encontrar una oferta de upselling
        mensajes = conversacion.mensajes
        oferta_encontrada = ""
        for msg in reversed(mensajes[-10:]):  # Últimos 10 mensajes
            if msg.role == "assistant":
                content_lower = msg.content.lower()
                # Buscar ofertas de upselling (preguntas con "?")
                if "?" in content_lower and any(kw in content_lower for kw in ["globo", "chocolate", "peluche", "complementar", "agregar"]):
                    oferta_encontrada = content_lower
                    break
        
        # Obtener IDs y nombres de productos ya en el carrito para no repetir
        carrito_ids = set()
        carrito_nombres = set()
        if conversacion.carrito and conversacion.carrito.items:
            for item in conversacion.carrito.items:
                carrito_ids.add(str(item.producto_id))
                carrito_nombres.add(item.producto_nombre.lower() if item.producto_nombre else "")
        
        productos = []
        texto = ""
        
        # Si no hay oferta de upselling reciente, no hacer nada
        if not oferta_encontrada:
            return None
        
        # Detectar qué se ofreció - ORDEN IMPORTA: globos primero porque es más específico
        if "globo" in oferta_encontrada:
            # Buscar globos
            try:
                globos = await self.mcp_service.buscar_productos("globos")
                if globos:
                    texto = "Aqui tienes los globos disponibles:"
                    for g in globos[:3]:
                        if g.get("ID") not in carrito_ids:
                            productos.append({
                                "id": g.get("ID", ""),
                                "nombre": g.get("Producto", ""),
                                "precio": f"S/{g.get('Precio_final', '')}",
                                "precio_num": float(str(g.get("Precio_final", "0")).replace(",", "")),
                                "imagen": self._convertir_drive_url(g.get("Foto", "")),
                                "categoria": g.get("Categoria", ""),
                                "tipo": g.get("Tipo", "")
                            })
            except Exception as e:
                print(f"[Error buscando globos] {e}")
        
        elif "chocolate" in oferta_encontrada:
            # Buscar chocolates solo si no hay chocolates en el carrito
            try:
                chocolates = await self.mcp_service.buscar_productos("chocolates")
                if chocolates:
                    # Filtrar los que ya están en el carrito (por ID o nombre)
                    chocolates_filtrados = []
                    for c in chocolates:
                        prod_id = str(c.get("ID", ""))
                        prod_nombre = c.get("Producto", "").lower()
                        # Verificar si ya está en carrito
                        if prod_id not in carrito_ids and not any(n in prod_nombre for n in carrito_nombres if n):
                            chocolates_filtrados.append(c)
                    
                    if chocolates_filtrados:
                        texto = "Excelente eleccion! Te muestro los chocolates:"
                        for choco in chocolates_filtrados[:3]:
                            productos.append({
                                "id": choco.get("ID", ""),
                                "nombre": choco.get("Producto", ""),
                                "precio": f"S/{choco.get('Precio_final', '')}",
                                "precio_num": float(str(choco.get("Precio_final", "0")).replace(",", "")),
                                "imagen": self._convertir_drive_url(choco.get("Foto", "")),
                                "categoria": choco.get("Categoria", ""),
                                "tipo": choco.get("Tipo", "")
                            })
                    else:
                        # Todos los chocolates ya están en el carrito
                        texto = "Ya tienes chocolates en tu carrito. Algo mas que necesites?"
            except Exception as e:
                print(f"[Error buscando chocolates] {e}")
        
        elif "peluche" in oferta_encontrada:
            # Buscar peluches y mostrar con fotos
            try:
                peluches = await self.mcp_service.buscar_productos("peluche")
                if peluches:
                    texto = "Aqui tienes los peluches disponibles:"
                    for p in peluches[:3]:
                        productos.append({
                            "id": p.get("ID", ""),
                            "nombre": p.get("Producto", ""),
                            "precio": f"S/{p.get('Precio_final', '')}",
                            "precio_num": float(str(p.get("Precio_final", "0")).replace(",", "")),
                            "imagen": self._convertir_drive_url(p.get("Foto", "")),
                            "categoria": p.get("Categoria", ""),
                            "tipo": p.get("Tipo", "")
                        })
            except Exception as e:
                print(f"[Error buscando peluches] {e}")
        
        if productos:
            burbujas = [texto]
            return {
                "texto": texto,
                "texto_limpio": texto,
                "burbujas": burbujas,
                "productos": productos,
                "acciones": [],
                "carrito": conversacion.carrito
            }
        
        return None
    
    async def _buscar_productos_proactivo(
        self, 
        mensaje: str, 
        conversacion: Conversacion
    ) -> str:
        """Busca productos cuando hay suficiente contexto + cross-selling"""
        
        contexto = conversacion.contexto or {}
        mensaje_lower = mensaje.lower()
        
        # Verificar contexto
        tiene_ocasion = "ocasion" in contexto
        tiene_preferencia = "color_preferido" in contexto or "flor_preferida" in contexto or "tipo_producto" in contexto
        tiene_presupuesto = "presupuesto_min" in contexto or "presupuesto_max" in contexto
        
        # Busqueda explicita
        busqueda_explicita = any(kw in mensaje_lower for kw in [
            "muestrame", "mostrar", "ver opciones", "que tienes", "opciones",
            "quiero ver", "enseñame", "tienen"
        ])
        
        # Busqueda por tipo de producto especifico (chocolates, peluches, etc)
        tiene_tipo = "tipo_producto" in contexto
        
        # Contexto suficiente: ocasion+presupuesto, o tipo+presupuesto, o busqueda explicita
        contexto_suficiente = (
            (tiene_ocasion and tiene_presupuesto) or
            (tiene_tipo and tiene_presupuesto) or
            (tiene_preferencia and tiene_presupuesto) or
            busqueda_explicita
        )
        
        
        if not contexto_suficiente:
            return ""
        
        # =====================================================
        # BUSCAR PRODUCTOS PRINCIPALES
        # =====================================================
        query_parts = []
        
        # Prioridad: tipo_producto > flor_preferida > ocasion > color
        if "tipo_producto" in contexto:
            query_parts.append(contexto["tipo_producto"])
        if "flor_preferida" in contexto:
            query_parts.append(contexto["flor_preferida"])
        if "ocasion" in contexto:
            query_parts.append(contexto["ocasion"])
        if "color_preferido" in contexto:
            query_parts.append(contexto["color_preferido"])
        
        query = " ".join(query_parts) if query_parts else mensaje
        presupuesto = float(contexto.get("presupuesto_max", 500))
        
        productos_principales = []
        try:
            if await self.mcp_service.is_available():
                productos_principales = await self.mcp_service.buscar_productos(query)
                
                # Fallback si no encuentra con la query completa
                if not productos_principales and len(query_parts) > 1:
                    # Intentar solo con ocasion
                    if "ocasion" in contexto:
                        productos_principales = await self.mcp_service.buscar_productos(contexto["ocasion"])
                    # O solo con tipo
                    elif "tipo_producto" in contexto:
                        productos_principales = await self.mcp_service.buscar_productos(contexto["tipo_producto"])
                
                # Fallback final: productos economicos
                if not productos_principales:
                    productos_principales = await self.mcp_service.productos_economicos(10)
        except Exception as e:
            print(f"[ERROR busqueda] {e}")
        
        if not productos_principales:
            return ""
        
        # Filtrar por presupuesto
        productos_filtrados = []
        for p in productos_principales:
            try:
                # Asegurar que p sea un diccionario
                if isinstance(p, dict):
                    precio = float(str(p.get("Precio_final", "0")).replace(",", ""))
                    if precio <= presupuesto:
                        productos_filtrados.append(p)
            except Exception as e:
                print(f"[ERROR filtrado] {e}")
        
        # Si no hay en presupuesto, mostrar los mas cercanos
        if not productos_filtrados:
            def get_precio_safe(x):
                try:
                    if isinstance(x, dict):
                        return float(str(x.get("Precio_final", "9999")).replace(",", ""))
                    return 9999
                except:
                    return 9999
            
            productos_filtrados = sorted(
                [p for p in productos_principales if isinstance(p, dict)],
                key=get_precio_safe
            )[:3]
        
        resultado = self._formatear_resultado_busqueda(productos_filtrados[:5])
        
        # =====================================================
        # CROSS-SELLING: Buscar complementos
        # =====================================================
        complementos = []
        ocasion = contexto.get("ocasion", "")
        tipo = contexto.get("tipo_producto", "")
        
        try:
            # Si compra flores -> ofrecer chocolates o peluche
            if any(t in tipo.lower() for t in ["flor", "ramo", "arreglo", "rosas"]) or \
               any(f in str(query).lower() for f in ["rosa", "tulipan", "girasol", "flor"]):
                choco = await self.mcp_service.buscar_productos("chocolates")
                if choco:
                    complementos.append(("Chocolates", choco[0]))
                peluche = await self.mcp_service.buscar_productos("peluche")
                if peluche:
                    complementos.append(("Peluche", peluche[0]))
            
            # Si compra peluche -> ofrecer flores
            elif "peluche" in tipo.lower() or "peluche" in str(query).lower():
                flores = await self.mcp_service.buscar_productos("rosas")
                if flores:
                    complementos.append(("Ramo de rosas", flores[0]))
            
            # Si es cumpleaños -> ofrecer globos
            if "cumple" in ocasion.lower():
                globos = await self.mcp_service.buscar_productos("globos")
                if globos:
                    # Buscar el de cumpleaños específicamente
                    globo_cumple = next((g for g in globos if "cumple" in g.get("Producto", "").lower()), globos[0])
                    complementos.append(("Globos", globo_cumple))
            
            # Buscar productos con descuento para upselling
            descuentos = await self.mcp_service.productos_con_descuento()
            if descuentos:
                # Filtrar descuentos relevantes a la ocasion
                for d in descuentos[:2]:
                    cat = d.get("Categoria", "").lower()
                    if ocasion.lower() in cat or cat in ocasion.lower():
                        complementos.append(("Oferta especial", d))
                        break
        except Exception as e:
            print(f"[ERROR cross-selling] {e}")
        
        # Formatear resultado con cross-selling
        cross_sell_text = ""
        if complementos:
            # Tomar el primer complemento relevante
            nombre_comp, prod_comp = complementos[0]
            precio_comp = prod_comp.get("Precio_final", "")
            prod_nombre_comp = prod_comp.get("Producto", "")
            prod_id_comp = prod_comp.get("ID", "")
            foto_comp = self._convertir_drive_url(prod_comp.get("Foto", ""))
            
            # Guardar producto de upselling en contexto para mostrarlo como tarjeta
            upsell_producto = {
                "id": prod_id_comp,
                "nombre": prod_nombre_comp,
                "precio": f"S/{precio_comp}",
                "precio_num": float(str(precio_comp).replace(",", "")),
                "imagen": foto_comp,
                "categoria": prod_comp.get("Categoria", ""),
                "tipo": prod_comp.get("Tipo", ""),
                "es_upsell": True
            }
            conversacion.actualizar_contexto("upsell_producto", upsell_producto)
            conversacion.actualizar_contexto("ultimo_upsell_id", prod_id_comp)
            
            # Solo decirle a Gemini que pregunte, la tarjeta se agrega automáticamente
            cross_sell_text = f"\n\nAl final pregunta: 'Te gustaria agregarlo?' (el producto de upselling ya se muestra como tarjeta)"
        
        return f"""
CATALOGO DISPONIBLE:
{resultado}
INSTRUCCIONES:
- Muestra 2-3 productos del catalogo usando [PRODUCTO:id|nombre|precio|url]
- NO incluyas productos de complemento/upselling en tu respuesta (se agregan automaticamente)
- {cross_sell_text if cross_sell_text else 'No hay upselling para esta busqueda'}
"""
    
    def _formatear_resultado_busqueda(self, resultados: Any) -> str:
        """Formatea los resultados de busqueda para el modelo"""
        if not resultados:
            return "No se encontraron productos."
        
        if isinstance(resultados, list) and len(resultados) > 0:
            lineas = []
            lineas.append("CATALOGO DISPONIBLE (copia estos datos exactamente):")
            lineas.append("")
            
            for i, p in enumerate(resultados[:5], 1):
                if isinstance(p, dict):
                    prod_id = p.get("ID", p.get("id", ""))
                    nombre = p.get("Producto", p.get("producto", "Producto")).strip()
                    precio_final = float(str(p.get("Precio_final", p.get("precio_final", 0))).replace(",", ""))
                    precio_original = float(str(p.get("Precio", p.get("precio", 0))).replace(",", ""))
                    categoria = p.get("Categoria", p.get("categoria", ""))
                    color = p.get("Color", p.get("color", ""))
                    descuento = float(p.get("Descuento", p.get("descuento", 0)) or 0)
                    foto_url = p.get("Foto", p.get("foto", ""))
                    stock = int(float(p.get("Stock", p.get("stock", 0)) or 0))
                    tipo = p.get("Tipo", p.get("tipo", ""))
                    
                    # Convertir URL de Drive a formato directo
                    imagen_directa = self._convertir_drive_url(foto_url)
                    
                    # Formato listo para usar: [PRODUCTO:id|nombre|precio|imagen]
                    lineas.append(f"[PRODUCTO:{prod_id}|{nombre}|{precio_final:.0f}|{imagen_directa}]")
                    
                    # Info adicional
                    extra = []
                    if tipo:
                        extra.append(tipo)
                    if color:
                        extra.append(f"Color: {color}")
                    if descuento > 0:
                        extra.append(f"Descuento: antes S/{precio_original:.0f}")
                    
                    if extra:
                        lineas.append(f"   ({', '.join(extra)})")
                    lineas.append("")
            
            return "\n".join(lineas)
        
        return "No se encontraron productos."
    
    def _obtener_hora_lima(self) -> dict:
        """Obtiene la hora actual en Lima, Peru"""
        ahora = datetime.now(LIMA_TZ)
        return {
            "hora": ahora.hour,
            "minuto": ahora.minute,
            "hora_formato": ahora.strftime("%I:%M %p"),
            "dia_semana": ahora.strftime("%A"),
            "fecha": ahora.strftime("%d/%m/%Y")
        }
    
    def _verificar_tienda_abierta(self, tienda: dict, hora_actual: int) -> bool:
        """Verifica si una tienda esta abierta"""
        return tienda["hora_apertura"] <= hora_actual < tienda["hora_cierre"]
    
    def _construir_contexto(self, conversacion: Conversacion) -> str:
        """Construye contexto adicional para el prompt"""
        contexto_parts = []
        
        # Agregar hora actual de Lima
        hora_lima = self._obtener_hora_lima()
        contexto_parts.append(f"HORA_ACTUAL_LIMA: {hora_lima['hora_formato']} ({hora_lima['dia_semana']})")
        
        # Estado de tiendas
        tiendas_status = []
        for tienda in TIENDAS_ROSATEL:
            abierta = self._verificar_tienda_abierta(tienda, hora_lima["hora"])
            estado = "ABIERTA" if abierta else "CERRADA"
            tiendas_status.append(f"- {tienda['nombre']}: {estado} (horario: {tienda['horario']})")
        contexto_parts.append("ESTADO TIENDAS:\n" + "\n".join(tiendas_status))
        
        if conversacion.carrito and conversacion.carrito.items:
            contexto_parts.append(f"CARRITO ACTUAL:\n{conversacion.carrito.to_chat_message()}")
        
        if conversacion.contexto:
            prefs = []
            if "ocasion" in conversacion.contexto:
                prefs.append(f"- Ocasion: {conversacion.contexto['ocasion']}")
            if "presupuesto_min" in conversacion.contexto:
                prefs.append(f"- Presupuesto: S/{conversacion.contexto.get('presupuesto_min', 0)} - S/{conversacion.contexto.get('presupuesto_max', 500)}")
            if "color_preferido" in conversacion.contexto:
                prefs.append(f"- Color preferido: {conversacion.contexto['color_preferido']}")
            if prefs:
                contexto_parts.append("PREFERENCIAS DEL CLIENTE:\n" + "\n".join(prefs))
        
        return "\n\n".join(contexto_parts)
    
    def _formatear_historial(self, conversacion: Conversacion, limit: int = 10) -> str:
        """Formatea el historial para el prompt"""
        mensajes = conversacion.mensajes[-limit:]
        historial = []
        
        for msg in mensajes:
            role = "Usuario" if msg.role == "user" else "Rosa"
            historial.append(f"{role}: {msg.content}")
        
        return "\n".join(historial) if historial else "(Primera interaccion)"
    
    async def _procesar_acciones(
        self, 
        respuesta: str,
        conversacion: Conversacion
    ) -> Tuple[str, List[dict], List[dict]]:
        """Procesa acciones especiales en la respuesta"""
        productos_display = []
        acciones = []
        respuesta_procesada = respuesta
        
        # Procesar productos con formato [PRODUCTO:id|nombre|precio|url]
        producto_matches = re.findall(self.action_patterns["PRODUCTO"], respuesta)
        for match_str in producto_matches:
            parts = match_str.split("|")
            if len(parts) >= 3:
                prod_id = parts[0].strip()
                nombre = parts[1].strip()
                precio = parts[2].strip()
                imagen_url = self._convertir_drive_url(parts[3].strip()) if len(parts) > 3 else ""
                
                producto_display = {
                    "id": prod_id,
                    "nombre": nombre,
                    "precio": f"S/{precio}",
                    "precio_num": float(precio) if precio.replace(".", "").isdigit() else 0,
                    "imagen": imagen_url
                }
                productos_display.append(producto_display)
                
                # Reemplazar el tag con texto formateado
                respuesta_procesada = respuesta_procesada.replace(
                    f"[PRODUCTO:{match_str}]", 
                    f"\n**{nombre}** - S/{precio}"
                )
                
                acciones.append({"tipo": "mostrar_producto", "producto": producto_display})
        
        # Buscar productos con [BUSCAR_PRODUCTO:query]
        match = re.search(self.action_patterns["BUSCAR_PRODUCTO"], respuesta)
        if match:
            query = match.group(1).strip()
            productos_encontrados = await self._ejecutar_busqueda(query)
            
            if productos_encontrados:
                for p in productos_encontrados[:3]:
                    imagen_url = self._convertir_drive_url(p.foto) if hasattr(p, 'foto') else ""
                    prod_display = {
                        "id": p.id if hasattr(p, 'id') else p.ID,
                        "nombre": p.producto if hasattr(p, 'producto') else p.Producto,
                        "precio": f"S/{p.precio_final if hasattr(p, 'precio_final') else p.Precio_final:.2f}",
                        "precio_num": float(p.precio_final if hasattr(p, 'precio_final') else p.Precio_final),
                        "imagen": imagen_url,
                        "descuento": float(p.descuento if hasattr(p, 'descuento') else p.Descuento) if (p.descuento if hasattr(p, 'descuento') else p.Descuento) else 0,
                        "precio_original": f"S/{p.precio if hasattr(p, 'precio') else p.Precio}" if (p.descuento if hasattr(p, 'descuento') else p.Descuento) else None
                    }
                    productos_display.append(prod_display)
                
                productos_texto = "\n".join([f"- **{p['nombre']}** - {p['precio']}" for p in productos_display])
                respuesta_procesada = respuesta_procesada.replace(match.group(0), f"\n{productos_texto}")
            else:
                respuesta_procesada = respuesta_procesada.replace(match.group(0), "\nNo encontre productos con esas caracteristicas. Quieres probar con algo diferente?")
            
            acciones.append({"tipo": "buscar", "query": query, "resultados": len(productos_encontrados)})
        
        # Agregar al carrito con [AGREGAR_CARRITO:id|nombre|precio]
        match = re.search(self.action_patterns["AGREGAR_CARRITO"], respuesta)
        if match:
            parts = match.group(1).strip().split("|")
            producto_id = parts[0].strip()
            nombre = parts[1].strip() if len(parts) > 1 else "Producto"
            try:
                precio = float(parts[2].strip()) if len(parts) > 2 else 0
            except:
                precio = 0
            
            # Siempre remover el tag de la respuesta
            respuesta_procesada = respuesta_procesada.replace(match.group(0), "")
            
            # Intentar obtener producto del BQ
            producto = None
            if producto_id.isdigit():
                producto = self.bq_service.obtener_producto(producto_id)
            
            # Si no encontramos por ID, buscar por nombre
            if not producto and nombre:
                productos_busqueda = self.bq_service.buscar_productos(nombre, limit=1)
                if productos_busqueda:
                    producto = productos_busqueda[0]
            
            if producto:
                if not conversacion.carrito:
                    conversacion.carrito = Carrito(session_id=conversacion.session_id)
                conversacion.carrito.agregar_item(producto, 1)
                
                # Limpiar contexto de upselling para no repetir ofertas
                if conversacion.contexto:
                    conversacion.contexto.pop("ultimo_upsell_id", None)
                
                acciones.append({
                    "tipo": "agregar_carrito", 
                    "producto_id": producto.id if hasattr(producto, 'id') else producto_id, 
                    "nombre": producto.producto if hasattr(producto, 'producto') else nombre,
                    "precio": precio
                })
        
        # Checkout con [CHECKOUT:codigo]
        match = re.search(self.action_patterns["CHECKOUT"], respuesta)
        if match:
            codigo = match.group(1).strip()
            if codigo == "codigo_random":
                codigo = self._generar_codigo_carrito()
            
            checkout_url = f"https://rosatel.pe/checkout/{codigo}"
            respuesta_procesada = respuesta_procesada.replace(
                match.group(0), 
                f"\n\nLink de pago: {checkout_url}"
            )
            
            acciones.append({
                "tipo": "checkout", 
                "codigo": codigo,
                "url": checkout_url,
                "carrito": conversacion.carrito.to_dict() if conversacion.carrito else None
            })
        
        # Ver carrito (legacy)
        if re.search(self.action_patterns["VER_CARRITO"], respuesta):
            carrito_msg = conversacion.carrito.to_chat_message() if conversacion.carrito else "Tu carrito esta vacio."
            respuesta_procesada = re.sub(self.action_patterns["VER_CARRITO"], f"\n{carrito_msg}", respuesta_procesada)
            acciones.append({"tipo": "ver_carrito"})
        
        # Generar checkout (legacy)
        if re.search(self.action_patterns["GENERAR_CHECKOUT"], respuesta):
            if conversacion.carrito and conversacion.carrito.items:
                codigo = self._generar_codigo_carrito()
                checkout_url = f"https://rosatel.pe/checkout/{codigo}"
                checkout_msg = f"""
Resumen de tu pedido:
{conversacion.carrito.to_chat_message()}

Link de pago: {checkout_url}
"""
                respuesta_procesada = re.sub(self.action_patterns["GENERAR_CHECKOUT"], checkout_msg, respuesta_procesada)
                acciones.append({"tipo": "checkout", "codigo": codigo, "url": checkout_url})
        
        return respuesta_procesada.strip(), productos_display, acciones
    
    async def _ejecutar_busqueda(self, query: str) -> List[Producto]:
        """Ejecuta busqueda usando MCP Toolbox o BigQuery"""
        try:
            # Intentar con MCP Toolbox primero
            if await self.mcp_service.is_available():
                resultados = await self.mcp_service.buscar_productos(query)
                if resultados:
                    return [Producto(**r) for r in resultados[:5]]
            
            # Fallback a BigQuery
            return self._parsear_busqueda(query)
        except Exception as e:
            print(f"Error en busqueda: {e}")
            return self._parsear_busqueda(query)
    
    def _parsear_busqueda(self, query: str) -> List[Producto]:
        """Parsea y ejecuta busqueda de productos"""
        precio_min = None
        precio_max = None
        
        precio_match = re.search(r'(\d+)\s*[-a]\s*(\d+)', query)
        if precio_match:
            precio_min = float(precio_match.group(1))
            precio_max = float(precio_match.group(2))
            query = re.sub(r'\d+\s*[-a]\s*\d+', '', query).strip()
        
        categoria = None
        categorias_keywords = {
            "flores": "Flores", "rosas": "Flores", "tulipanes": "Flores",
            "girasoles": "Flores", "orquideas": "Flores",
            "peluches": "Peluches", "osos": "Peluches",
            "chocolates": "Chocolates", "combos": "Combos"
        }
        
        query_lower = query.lower()
        for keyword, cat in categorias_keywords.items():
            if keyword in query_lower:
                categoria = cat
                break
        
        color = None
        colores = ["rojo", "rosa", "blanco", "amarillo", "naranja", "morado", "azul", "multicolor"]
        for c in colores:
            if c in query_lower:
                color = c.capitalize()
                break
        
        return self.bq_service.buscar_productos(
            query=query, categoria=categoria, color=color,
            precio_min=precio_min, precio_max=precio_max, limit=5
        )
    
    async def _respuesta_demo(self, mensaje: str, conversacion: Conversacion) -> str:
        """Respuesta inteligente usando contexto de la conversacion"""
        mensaje_lower = mensaje.lower().strip()
        contexto = conversacion.contexto or {}
        
        # Extraer preferencias del mensaje actual
        self.extraer_preferencias(mensaje, conversacion)
        
        # === RESPUESTAS RAPIDAS (sin buscar productos) ===
        
        # Saludos
        if mensaje_lower in ["hola", "hi", "buenos dias", "buenas tardes", "buenas noches", "buenas"]:
            return "Hola! Que andas buscando?"
        
        # Horarios/tiendas
        if any(p in mensaje_lower for p in ["abierto", "abren", "horario", "tienda"]):
            hora_lima = self._obtener_hora_lima()
            tiendas = []
            for t in TIENDAS_ROSATEL:
                estado = "abierta" if self._verificar_tienda_abierta(t, hora_lima["hora"]) else "cerrada"
                tiendas.append(f"- {t['nombre']}: {t['horario']} ({estado})")
            return f"Online 24/7 con envio a todo Lima.|NUEVA_BURBUJA|Tiendas:|NUEVA_BURBUJA|" + "\n".join(tiendas)
        
        # === DETECTAR ACEPTACION (ok, si, dale, etc) ===
        if mensaje_lower in ["ok", "si", "sí", "dale", "va", "bueno", "esta bien", "de acuerdo", "perfecto"]:
            # Revisar ultimo mensaje del bot para entender contexto
            ultimo_bot = ""
            for m in reversed(conversacion.mensajes):
                if m.role == "assistant":
                    ultimo_bot = m.content.lower()
                    break
            
            # Si sugerimos subir presupuesto
            if "s/" in ultimo_bot and "te puedo mostrar" in ultimo_bot:
                match = re.search(r's/(\d+)', ultimo_bot)
                if match:
                    nuevo_presupuesto = float(match.group(1))
                    conversacion.actualizar_contexto("presupuesto_max", nuevo_presupuesto)
        
        # === EXTRAER INFO DEL MENSAJE ===
        contexto = conversacion.contexto or {}
        
        # Detectar presupuesto
        pres_match = re.search(r'(\d+)\s*(?:soles?)?', mensaje_lower)
        if pres_match:
            monto = float(pres_match.group(1))
            if monto >= 30:
                conversacion.actualizar_contexto("presupuesto_max", monto)
        
        # Detectar color
        for color in ["rojo", "rosa", "blanco", "amarillo", "variado", "pasteles"]:
            if color in mensaje_lower:
                conversacion.actualizar_contexto("color_preferido", color)
                break
        
        # Detectar ocasion (guardar con nombre correcto para BigQuery)
        ocasion_map = {
            "Cumpleaños": ["cumple", "cumpleaños", "cumpleanos", "birthday"],
            "Aniversario": ["aniversario", "anniversary"],
            "Amor": ["novia", "novio", "esposa", "esposo", "enamorada", "amor", "romantico"],
            "Día de la Madre": ["mama", "madre", "dia de la madre"],
            "Condolencias": ["funeral", "condolencia", "fallecio", "pesame"],
            "Amistad": ["amiga", "amigo", "amistad"],
            "Graduación": ["graduacion", "graduado", "egresado"],
            "Para Niños": ["niño", "niña", "hijo", "hija", "bebe"]
        }
        for ocasion, keywords in ocasion_map.items():
            if any(k in mensaje_lower for k in keywords):
                conversacion.actualizar_contexto("ocasion", ocasion)
                break
        
        # Recargar contexto
        contexto = conversacion.contexto or {}
        tiene_ocasion = "ocasion" in contexto
        tiene_presupuesto = "presupuesto_max" in contexto
        
        # === SI TENEMOS SUFICIENTE INFO -> BUSCAR PRODUCTOS ===
        if tiene_ocasion and tiene_presupuesto:
            presupuesto = float(contexto.get("presupuesto_max", 150))
            ocasion = contexto.get("ocasion", "")
            color = contexto.get("color_preferido", "")
            
            # La ocasion ya tiene el nombre correcto de categoria (con tildes)
            query = ocasion if ocasion else "flores"
            if color:
                query += " " + color
            
            try:
                # Usar MCP para buscar
                print(f"[DEBUG] Buscando productos con query: '{query}' y presupuesto: {presupuesto}")
                productos_raw = await self.mcp_service.buscar_productos(query)
                print(f"[DEBUG] Productos encontrados: {len(productos_raw) if productos_raw else 0}")
                
                if not productos_raw:
                    print("[DEBUG] No se encontraron productos, buscando 'flores'")
                    productos_raw = await self.mcp_service.buscar_productos("flores")
                
                # Filtrar por precio (convertir string a float)
                productos_ok = []
                for p in productos_raw:
                    try:
                        precio = float(str(p.get("Precio_final", "0")).replace(",", ""))
                        if precio <= presupuesto:
                            productos_ok.append(p)
                    except:
                        pass
                
                if productos_ok:
                    # Tomar los 3 mejores
                    mostrar = productos_ok[:3]
                    
                    respuesta = "Mira estas opciones:"
                    for p in mostrar:
                        pid = p.get("ID", "")
                        nombre = str(p.get("Producto", "")).strip()
                        precio = float(str(p.get("Precio_final", "0")).replace(",", ""))
                        foto = p.get("Foto", "")
                        tipo = p.get("Tipo", "")
                        imagen = self._convertir_drive_url(foto)
                        
                        respuesta += f"\n[PRODUCTO:{pid}|{nombre}|{precio:.0f}|{imagen}]"
                    
                    # Upselling: buscar complementos
                    if "flor" in tipo.lower() or "ramo" in tipo.lower() or "arreglo" in tipo.lower():
                        respuesta += "|NUEVA_BURBUJA|Si quieres, puedo agregarte chocolates Ferrero (S/35) o un peluche (desde S/79)."
                    elif "peluche" in tipo.lower():
                        respuesta += "|NUEVA_BURBUJA|Tambien tenemos packs con flores y chocolates. Te muestro?"
                    
                    return respuesta
                else:
                    # No hay en ese rango
                    nuevo = int(presupuesto) + 50
                    conversacion.actualizar_contexto("presupuesto_sugerido", nuevo)
                    return f"En S/{int(presupuesto)} no hay muchas opciones. Con S/{nuevo} te muestro mejores arreglos. Dale?"
                    
            except Exception as e:
                print(f"Error MCP: {e}")
                import traceback
                traceback.print_exc()
        
        # === SI FALTA INFO -> PREGUNTAR ===
        
        # Falta ocasion
        if not tiene_ocasion:
            if any(p in mensaje_lower for p in ["rosa", "rosas", "flores", "regalo", "quiero", "busco", "tienen"]):
                return "Para que ocasion seria?"
            if any(p in mensaje_lower for p in ["peluche", "oso", "hugo"]):
                return "Que lindo! Es para cumpleanos, para ninos, o regalo romantico?"
            return "Que andas buscando?"
        
        # Tiene ocasion pero falta presupuesto
        if tiene_ocasion and not tiene_presupuesto:
            return "Y mas o menos cuanto pensabas gastar?"
        
        # === OTRAS RESPUESTAS ===
        if any(p in mensaje_lower for p in ["envio", "delivery"]):
            return "Envio a todo Lima en 24-48h. Costo: S/15-25."
        
        if "carrito" in mensaje_lower:
            return "Tu carrito esta vacio. Que quieres agregar?"
        
        return "Cuentame mas. Que ocasion es y cuanto quieres gastar?"
    
    async def _buscar_con_descuento(self) -> list:
        """Busca productos con descuento para upselling"""
        try:
            if await self.mcp_service.is_available():
                from services.mcp_toolbox import get_mcp_service
                mcp = get_mcp_service()
                resultados = await mcp.productos_con_descuento()
                if resultados:
                    return [Producto(**r) for r in resultados[:2]]
        except:
            pass
        return []
    
    def extraer_preferencias(self, mensaje: str, conversacion: Conversacion):
        """Extrae y guarda preferencias del mensaje del usuario - Basado en categorias de BigQuery"""
        mensaje_lower = mensaje.lower()
        
        # =====================================================
        # CATEGORIAS DE BIGQUERY CON KEYWORDS COMPLETAS
        # =====================================================
        ocasiones = {
            # Amistad (10 productos)
            "Amistad": [
                "amiga", "amigo", "amistad", "companero", "companera", "colega",
                "jefe", "jefa", "trabajo", "oficina", "vecino", "vecina",
                "conocido", "gracias", "agradecer", "agradecimiento", "detalle"
            ],
            # Amor (5 productos)
            "Amor": [
                "novia", "novio", "esposa", "esposo", "amor", "romantico", "romantica",
                "enamorado", "enamorada", "pareja", "san valentin", "valentin",
                "te amo", "te quiero", "mi amor", "corazon"
            ],
            # Cumpleaños (5 productos)
            "Cumpleaños": [
                "cumpleanos", "cumple", "birthday", "cumpleaños", "anos", "años",
                "feliz cumple", "felicitacion", "felicitar"
            ],
            # Graduación (5 productos)
            "Graduación": [
                "graduacion", "graduado", "graduada", "egresado", "egresada",
                "titulo", "universidad", "colegio", "promocion", "bachiller",
                "licenciado", "ingeniero", "doctor", "magister"
            ],
            # Aniversario (5 productos)
            "Aniversario": [
                "aniversario", "anniversary", "bodas", "anos juntos", "años juntos",
                "celebrar", "fecha especial"
            ],
            # Condolencias (5 productos)
            "Condolencias": [
                "condolencias", "pesame", "funeral", "fallecio", "fallecimiento",
                "murio", "muerte", "velorio", "sepelio", "duelo", "luto",
                "descanse en paz", "qepd", "sentido pesame"
            ],
            # Inauguraciones (3 productos)
            "Inauguraciones": [
                "inauguracion", "apertura", "nuevo local", "nueva tienda",
                "nuevo negocio", "emprendimiento", "empresa nueva", "oficina nueva"
            ],
            # Mejórate Pronto (3 productos)
            "Mejórate Pronto": [
                "mejorate", "enfermo", "enferma", "hospital", "clinica", "operacion",
                "recuperacion", "salud", "animo", "fuerza", "pronta recuperacion"
            ],
            # Nacimiento (3 productos)
            "Nacimiento": [
                "nacimiento", "bebe", "bebé", "recien nacido", "nacio", "parto",
                "maternidad", "baby shower", "embarazada", "nena", "nene"
            ],
            # Matrimonio (3 productos)
            "Matrimonio": [
                "matrimonio", "boda", "casamiento", "novia", "novios", "casarse",
                "compromiso", "pedida de mano", "civil", "iglesia"
            ],
            # Para Él (3 productos)
            "Para Él": [
                "papa", "papá", "padre", "dia del padre", "abuelo", "hermano",
                "tio", "suegro", "cunado", "para el", "hombre", "varon",
                "masculino", "caballero"
            ],
            # Para su escritorio (3 productos)
            "Para su escritorio": [
                "escritorio", "oficina", "decoracion", "decorar", "desk",
                "trabajo", "despacho", "preservada", "seca"
            ],
            # Para Niños (2 productos)
            "Para Niños": [
                "nino", "niño", "nina", "niña", "hijo", "hija", "nietos",
                "sobrino", "sobrina", "pequeño", "pequeña", "infantil", "kids"
            ],
            # Variado (productos generales)
            "Variado": [
                "globos", "complemento", "adicional", "extra"
            ]
        }
        
        for ocasion, keywords in ocasiones.items():
            if any(kw in mensaje_lower for kw in keywords):
                conversacion.actualizar_contexto("ocasion", ocasion)
                break
        
        # =====================================================
        # DETECTAR PRESUPUESTO (multiples formatos)
        # =====================================================
        # Formato: "100 soles", "s/100", "S/.100", "menos de 100", "hasta 100", "maximo 100"
        patrones_precio = [
            r'(?:menos de|hasta|maximo|max|presupuesto de?)\s*(?:s/?\.?\s*)?(\d+)',
            r's/?\.?\s*(\d+)',
            r'(\d+)\s*(?:soles?|sol)',
            r'tengo\s*(\d+)',
            r'gastar\s*(?:unos?)?\s*(\d+)'
        ]
        
        for patron in patrones_precio:
            precio_match = re.search(patron, mensaje_lower)
            if precio_match:
                monto = float(precio_match.group(1))
                if monto >= 30:
                    conversacion.actualizar_contexto("presupuesto_max", monto)
                    break
        
        # Rango de precios: "100 a 200", "entre 100 y 200"
        rango_match = re.search(r'(?:entre\s*)?(\d+)\s*(?:a|y|-|hasta)\s*(\d+)', mensaje_lower)
        if rango_match:
            conversacion.actualizar_contexto("presupuesto_min", float(rango_match.group(1)))
            conversacion.actualizar_contexto("presupuesto_max", float(rango_match.group(2)))
        
        # =====================================================
        # COLORES
        # =====================================================
        colores = {
            "rojo": ["rojo", "rojas", "rojos", "red"],
            "rosa": ["rosa", "rosado", "rosada", "pink", "fucsia"],
            "blanco": ["blanco", "blanca", "blancos", "white", "crema"],
            "amarillo": ["amarillo", "amarilla", "amarillos", "yellow"],
            "naranja": ["naranja", "anaranjado", "orange"],
            "morado": ["morado", "morada", "purpura", "lila", "violeta"],
            "azul": ["azul", "celeste", "blue"],
            "variado": ["variado", "colores", "multicolor", "surtido", "mix"]
        }
        
        for color_key, keywords in colores.items():
            if any(kw in mensaje_lower for kw in keywords):
                conversacion.actualizar_contexto("color_preferido", color_key)
                break
        
        # =====================================================
        # TIPOS DE FLORES
        # =====================================================
        flores = {
            "rosas": ["rosa", "rosas", "rose", "roses"],
            "tulipanes": ["tulipan", "tulipanes", "tulips"],
            "girasoles": ["girasol", "girasoles", "sunflower"],
            "orquideas": ["orquidea", "orquideas", "orchid"],
            "liliums": ["lilium", "liliums", "lirio", "lirios", "lily"],
            "astromelias": ["astromelia", "astromelias", "alstroemeria"],
            "gladiolos": ["gladiolo", "gladiolos"]
        }
        
        for flor_key, keywords in flores.items():
            if any(kw in mensaje_lower for kw in keywords):
                conversacion.actualizar_contexto("flor_preferida", flor_key)
                break
        
        # =====================================================
        # TIPOS DE PRODUCTO (para cross-selling)
        # =====================================================
        tipos_producto = {
            "Peluche": ["peluche", "oso", "osito", "hugo", "kodi", "muñeco"],
            "Chocolates": ["chocolate", "chocolates", "ferrero", "iberica", "bombones", "dulces"],
            "Vino": ["vino", "vinos", "tinto", "blanco", "espumante", "champagne", "licor"],
            "Arreglo Floral": ["arreglo", "centro de mesa", "florero"],
            "Ramo": ["ramo", "bouquet", "ramillete"],
            "Caja Flores": ["caja", "box"],
            "Corona Fúnebre": ["corona", "lagrima", "funebre"],
            "Globos": ["globo", "globos"]
        }
        
        for tipo_key, keywords in tipos_producto.items():
            if any(kw in mensaje_lower for kw in keywords):
                conversacion.actualizar_contexto("tipo_producto", tipo_key)
                break
        
        # =====================================================
        # INTENCIONES ESPECIALES
        # =====================================================
        if any(kw in mensaje_lower for kw in ["barato", "economico", "económico", "poco presupuesto", "ajustado"]):
            conversacion.actualizar_contexto("busca_economico", True)
        
        if any(kw in mensaje_lower for kw in ["oferta", "descuento", "promocion", "rebaja"]):
            conversacion.actualizar_contexto("busca_descuento", True)
        
        if any(kw in mensaje_lower for kw in ["premium", "lujoso", "elegante", "especial", "grande"]):
            conversacion.actualizar_contexto("busca_premium", True)


@lru_cache()
def get_ai_brain() -> AIBrain:
    """Obtiene instancia singleton del cerebro IA"""
    return AIBrain()
