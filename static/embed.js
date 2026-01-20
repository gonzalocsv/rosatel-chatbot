/**
 * ================================================================================
 *                    ROSATEL WIDGET - SCRIPT EMBEBIBLE
 * ================================================================================
 * 
 * Uso:
 * <script src="https://tu-dominio.com/static/embed.js" 
 *         data-api-key="tu-api-key"
 *         data-server="https://tu-dominio.com"></script>
 */

(function() {
    'use strict';

    // Obtener configuracion del script
    const currentScript = document.currentScript;
    const apiKey = currentScript.getAttribute('data-api-key') || '';
    const serverUrl = currentScript.getAttribute('data-server') || '';

    if (!serverUrl) {
        console.error('Rosatel Widget: Falta data-server');
        return;
    }

    // Configuracion global
    window.ROSATEL_CONFIG = {
        apiKey: apiKey,
        serverUrl: serverUrl.replace(/\/$/, '')
    };

    // Crear contenedor del widget
    const container = document.createElement('div');
    container.id = 'rosatel-widget-container';
    document.body.appendChild(container);

    // Cargar estilos
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `${serverUrl}/static/widget.css`;
    document.head.appendChild(link);

    // Cargar fuente
    const fontLink = document.createElement('link');
    fontLink.rel = 'stylesheet';
    fontLink.href = 'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap';
    document.head.appendChild(fontLink);

    // Crear HTML del widget
    container.innerHTML = `
        <div class="rosatel-widget">
            <!-- Boton flotante -->
            <button class="widget-toggle" id="widget-toggle" aria-label="Abrir chat">
                <svg class="icon-chat" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
                <svg class="icon-close" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>

            <!-- Ventana de chat -->
            <div class="widget-window" id="widget-window">
                <div class="widget-header">
                    <div class="header-avatar">
                        <img src="https://www.rosatel.pe/static/version1736532164/frontend/Starter/starter_theme/es_PE/images/logo.svg" alt="Rosatel" style="width: 28px; height: 28px; object-fit: contain;" onerror="this.outerHTML='<span style=font-size:24px;color:#D4145A;font-weight:700>R</span>'">
                        <span class="status-indicator"></span>
                    </div>
                    <div class="header-info">
                        <h3 class="header-name">Rosa</h3>
                        <p class="header-status">Disponible</p>
                    </div>
                    <button class="header-close" id="header-close" aria-label="Cerrar chat">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </div>

                <div class="widget-messages" id="widget-messages"></div>

                <div class="widget-input-area">
                    <div class="input-container">
                        <input type="text" id="widget-input" class="widget-input" placeholder="Escribe tu mensaje..." autocomplete="off">
                        <button class="send-btn" id="send-btn" aria-label="Enviar">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="22" y1="2" x2="11" y2="13"></line>
                                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                            </svg>
                        </button>
                    </div>
                </div>

                <div class="widget-footer">
                    <span>Powered by</span>
                    <a href="#" target="_blank" class="footer-link">Chatiando</a>
                </div>
            </div>
        </div>
    `;

    // Configuracion para el script principal
    window.WIDGET_CONFIG = {
        apiKey: apiKey,
        apiUrl: serverUrl,
        botName: 'Rosa'
    };

    // Cargar script principal
    const script = document.createElement('script');
    script.src = `${serverUrl}/static/widget.js`;
    script.onload = function() {
        console.log('Rosatel Widget cargado correctamente');
    };
    document.body.appendChild(script);

})();
