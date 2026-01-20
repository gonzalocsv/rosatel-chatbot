"""
================================================================================
                    ROSATEL CHATBOT - MAIN APPLICATION
================================================================================
                    Chatbot de ventas para florería Rosatel
                    Canales: WhatsApp, Instagram, Widget Web
================================================================================
"""

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from contextlib import asynccontextmanager
import uvicorn
import secrets
import os

from config import get_settings
from routers import whatsapp_router, instagram_router, widget_router


settings = get_settings()
security = HTTPBasic()

# Password protection
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Maneja el ciclo de vida de la aplicación"""
    # Startup
    print("=" * 60)
    print("ROSATEL CHATBOT - Iniciando...")
    print("=" * 60)
    print(f"   Bot: {settings.bot_name}")
    print(f"   Empresa: {settings.company_name}")
    print(f"   Modelo IA: {settings.gemini_model}")
    print(f"   BigQuery: {settings.google_project_id}.{settings.bigquery_dataset}")
    print("=" * 60)
    
    # Inicializar servicios
    from services.session_manager import get_session_manager
    from services.bigquery_service import get_bigquery_service
    from services.ai_brain import get_ai_brain
    
    session_manager = get_session_manager()
    bq_service = get_bigquery_service()
    ai_brain = get_ai_brain()
    
    print(f"   Redis: {'Conectado' if session_manager.is_connected else 'Usando memoria local'}")
    print(f"   BigQuery: {'Conectado' if bq_service.bq.is_connected else 'Usando datos demo'}")
    print(f"   Gemini: {'Configurado' if ai_brain.model else 'Usando respuestas demo'}")
    print("=" * 60)
    print("Servidor listo!")
    print("=" * 60)
    
    yield
    
    # Shutdown
    print("\nApagando Rosatel Chatbot...")


# Crear aplicación FastAPI
app = FastAPI(
    title="Rosatel Chatbot API",
    description="""
    **Rosatel Chatbot** - Asistente virtual de ventas
    
    Chatbot inteligente para la floreria Rosatel que ayuda a los clientes a:
    - Encontrar el regalo perfecto para cada ocasion
    - Ver productos con fotos y precios
    - Agregar productos al carrito
    - Completar pedidos
    
    ## Canales soportados:
    - WhatsApp Cloud API
    - Instagram Messaging API
    - Widget Web embebible
    
    ## Endpoints principales:
    - `/webhook/whatsapp` - Webhook para WhatsApp
    - `/webhook/instagram` - Webhook para Instagram
    - `/widget/*` - API para widget web
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Registrar routers
app.include_router(whatsapp_router)
app.include_router(instagram_router)
app.include_router(widget_router)


@app.get("/", response_class=HTMLResponse)
async def home(authenticated: bool = Depends(verify_credentials)):
    """Pagina de inicio - protegida con password"""
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Rosatel Chatbot</title>
        <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
                background: linear-gradient(145deg, #FFF5F7 0%, #FCE4EC 50%, #F8BBD9 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #333;
            }
            .container {
                text-align: center;
                padding: 40px;
                max-width: 520px;
            }
            .logo {
                width: 120px;
                height: auto;
                margin-bottom: 16px;
            }
            h1 {
                font-size: 42px;
                margin-bottom: 8px;
                color: #D4145A;
                font-weight: 700;
            }
            .subtitle {
                font-size: 18px;
                color: #666;
                margin-bottom: 36px;
            }
            .card {
                background: white;
                border-radius: 20px;
                padding: 32px;
                color: #333;
                box-shadow: 0 4px 24px rgba(212, 20, 90, 0.12);
            }
            .card h2 {
                color: #D4145A;
                margin-bottom: 16px;
                font-size: 22px;
            }
            .card p {
                color: #666;
                line-height: 1.6;
            }
            .links {
                display: flex;
                flex-direction: column;
                gap: 12px;
                margin-top: 24px;
            }
            .link {
                display: block;
                padding: 14px 24px;
                background: #FAFAFA;
                border-radius: 12px;
                text-decoration: none;
                color: #333;
                font-weight: 500;
                transition: all 0.2s;
                border: 1px solid #F0E0E5;
            }
            .link:hover {
                background: #D4145A;
                color: white;
                border-color: #D4145A;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(212, 20, 90, 0.2);
            }
            .status {
                margin-top: 24px;
                padding: 14px;
                background: #F0FDF4;
                border-radius: 10px;
                color: #166534;
                font-size: 14px;
                border: 1px solid #BBF7D0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <img src="https://www.rosatel.pe/static/version1736532164/frontend/Starter/starter_theme/es_PE/images/logo.svg" alt="Rosatel" class="logo" onerror="this.style.display='none'">
            <h1>Rosatel</h1>
            <p class="subtitle">Chatbot de Ventas</p>
            
            <div class="card">
                <h2>Bienvenido</h2>
                <p>
                    Soy Rosa, tu asistente virtual. Estoy aqui para ayudarte 
                    a encontrar el regalo perfecto.
                </p>
                
                <div class="links">
                    <a href="/widget/embed" class="link">
                        Probar Widget de Chat
                    </a>
                    <a href="/docs" class="link">
                        Documentacion API
                    </a>
                    <a href="/widget/health" class="link">
                        Estado del Sistema
                    </a>
                </div>
                
                <div class="status">
                    Sistema operativo
                </div>
            </div>
        </div>
    </body>
    </html>
    """


@app.get("/health")
async def health():
    """Health check general"""
    return {
        "status": "ok",
        "service": "Rosatel Chatbot",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )
