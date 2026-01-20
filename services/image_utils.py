"""
================================================================================
                    UTILIDADES PARA MANEJO DE IMÁGENES
================================================================================
"""

import re
from typing import Optional


def convert_drive_url(url: str) -> Optional[str]:
    """
    Convierte URL de Google Drive a URL de imagen directa.
    
    Soporta múltiples formatos de URLs de Drive:
    - https://drive.google.com/file/d/{ID}/view
    - https://drive.google.com/open?id={ID}
    - https://drive.google.com/uc?id={ID}
    - https://docs.google.com/uc?id={ID}
    
    Args:
        url: URL original de Google Drive
        
    Returns:
        URL directa de la imagen o None si no es válida
    """
    if not url:
        return None
    
    # Si ya es una URL directa, retornarla
    if "uc?export=view" in url:
        return url
    
    # Patrón: /file/d/{ID}/ o /d/{ID}/
    match = re.search(r'/(?:file/)?d/([a-zA-Z0-9_-]+)', url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    
    # Patrón: ?id={ID} o &id={ID}
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    
    # Si no coincide con ningún patrón, retornar la URL original
    return url


def get_image_thumbnail(url: str, size: str = "w400") -> Optional[str]:
    """
    Genera URL de thumbnail para imágenes de Drive.
    
    Args:
        url: URL de la imagen
        size: Tamaño del thumbnail (w200, w400, w800, etc.)
        
    Returns:
        URL del thumbnail
    """
    if not url:
        return None
    
    # Convertir a URL directa primero
    direct_url = convert_drive_url(url)
    
    if not direct_url:
        return None
    
    # Extraer el ID
    match = re.search(r'id=([a-zA-Z0-9_-]+)', direct_url)
    if match:
        file_id = match.group(1)
        # URL de thumbnail con tamaño específico
        return f"https://drive.google.com/thumbnail?id={file_id}&sz={size}"
    
    return direct_url


def is_valid_image_url(url: str) -> bool:
    """
    Verifica si una URL parece ser una imagen válida.
    
    Args:
        url: URL a verificar
        
    Returns:
        True si parece ser una imagen válida
    """
    if not url:
        return False
    
    # Extensiones de imagen comunes
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    
    # Verificar extensión
    url_lower = url.lower()
    for ext in image_extensions:
        if ext in url_lower:
            return True
    
    # Verificar si es URL de Google Drive
    if 'drive.google.com' in url or 'docs.google.com' in url:
        return True
    
    # Verificar si tiene parámetros de imagen
    if any(param in url_lower for param in ['image', 'photo', 'pic', 'img']):
        return True
    
    return False


def format_product_image_html(url: str, alt: str = "Producto", width: int = 200) -> str:
    """
    Genera HTML para mostrar imagen de producto.
    
    Args:
        url: URL de la imagen
        alt: Texto alternativo
        width: Ancho de la imagen
        
    Returns:
        HTML de la imagen
    """
    direct_url = convert_drive_url(url) or url
    thumbnail_url = get_image_thumbnail(url, f"w{width}")
    
    return f'''
    <img 
        src="{thumbnail_url or direct_url}" 
        alt="{alt}"
        width="{width}"
        loading="lazy"
        onerror="this.style.display='none'"
        style="border-radius: 8px; object-fit: cover;"
    />
    '''


def format_product_image_whatsapp(url: str) -> dict:
    """
    Genera estructura para enviar imagen por WhatsApp.
    
    Args:
        url: URL de la imagen
        
    Returns:
        Diccionario con estructura de mensaje de imagen
    """
    direct_url = convert_drive_url(url)
    
    return {
        "type": "image",
        "image": {
            "link": direct_url
        }
    }


def extract_drive_file_id(url: str) -> Optional[str]:
    """
    Extrae el ID del archivo de una URL de Google Drive.
    
    Args:
        url: URL de Google Drive
        
    Returns:
        ID del archivo o None
    """
    if not url:
        return None
    
    # Patrón: /file/d/{ID}/ o /d/{ID}/
    match = re.search(r'/(?:file/)?d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # Patrón: ?id={ID} o &id={ID}
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    return None
