"""
Routers module for Rosatel Chatbot
"""

from .webhook_whatsapp import router as whatsapp_router
from .webhook_instagram import router as instagram_router
from .widget import router as widget_router

__all__ = [
    "whatsapp_router",
    "instagram_router", 
    "widget_router"
]
