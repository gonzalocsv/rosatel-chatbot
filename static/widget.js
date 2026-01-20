/**
 * ================================================================================
 *                         ROSATEL WIDGET - JAVASCRIPT
 * ================================================================================
 */

(function() {
    'use strict';

    // Estado del widget
    const state = {
        sessionId: null,
        isOpen: false,
        isTyping: false,
        messages: [],
        cart: [],  // Carrito de compras
        showCheckoutOnNext: false  // Flag para mostrar botón checkout después de agregar al carrito
    };
    
    // Limpiar sesion al cargar pagina (refrescar = nuevo chat)
    localStorage.removeItem('rosatel_session');

    // Elementos del DOM
    let elements = {};

    // Inicializacion
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        // Obtener elementos
        elements = {
            toggle: document.getElementById('widget-toggle'),
            window: document.getElementById('widget-window'),
            messages: document.getElementById('widget-messages'),
            input: document.getElementById('widget-input'),
            sendBtn: document.getElementById('send-btn'),
            headerClose: document.getElementById('header-close')
        };

        // Event listeners
        elements.toggle.addEventListener('click', toggleWidget);
        elements.headerClose.addEventListener('click', closeWidget);
        elements.sendBtn.addEventListener('click', sendMessage);
        elements.input.addEventListener('keypress', handleKeyPress);

        // Cargar sesion existente
        loadSession();

        // Animacion de pulso inicial
        setTimeout(() => {
            elements.toggle.classList.add('pulse');
        }, 2000);

        console.log('Rosatel Widget inicializado');
    }

    function toggleWidget() {
        state.isOpen = !state.isOpen;
        
        elements.toggle.classList.toggle('active', state.isOpen);
        elements.window.classList.toggle('open', state.isOpen);
        elements.toggle.classList.remove('pulse');

        if (state.isOpen && !state.sessionId) {
            iniciarChat();
        }

        if (state.isOpen) {
            setTimeout(() => elements.input.focus(), 300);
        }
    }

    function closeWidget() {
        state.isOpen = false;
        elements.toggle.classList.remove('active');
        elements.window.classList.remove('open');
    }

    function handleKeyPress(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    async function loadSession() {
        const savedSession = localStorage.getItem('rosatel_session');
        if (savedSession) {
            try {
                const data = JSON.parse(savedSession);
                state.sessionId = data.sessionId;
                state.messages = data.messages || [];
                renderMessages();
            } catch (e) {
                console.error('Error cargando sesion:', e);
            }
        }
    }

    function saveSession() {
        localStorage.setItem('rosatel_session', JSON.stringify({
            sessionId: state.sessionId,
            messages: state.messages.slice(-50)
        }));
    }

    async function iniciarChat() {
        try {
            const response = await fetch(`${WIDGET_CONFIG.apiUrl}/widget/chat/iniciar`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': WIDGET_CONFIG.apiKey
                },
                body: JSON.stringify({ session_id: state.sessionId })
            });

            if (!response.ok) throw new Error('Error iniciando chat');

            const data = await response.json();
            state.sessionId = data.session_id;

            // Agregar mensaje de bienvenida si es nueva sesion
            if (state.messages.length === 0) {
                addMessage('bot', data.mensaje_bienvenida);
            }

            saveSession();
        } catch (error) {
            console.error('Error iniciando chat:', error);
            addMessage('bot', 'Hola! Soy Rosa de Rosatel. Buscas algo especial hoy?');
        }
    }

    async function sendMessage() {
        const texto = elements.input.value.trim();
        if (!texto || state.isTyping) return;

        // Limpiar input
        elements.input.value = '';

        // Agregar mensaje del usuario
        addMessage('user', texto);

        // Mostrar typing indicator con delay inicial (simula que lee el mensaje)
        showTyping();
        await new Promise(resolve => setTimeout(resolve, 800));

        try {
            const response = await fetch(`${WIDGET_CONFIG.apiUrl}/widget/chat/mensaje`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': WIDGET_CONFIG.apiKey
                },
                body: JSON.stringify({
                    session_id: state.sessionId,
                    mensaje: texto
                })
            });

            hideTyping();

            if (!response.ok) throw new Error('Error enviando mensaje');

            const data = await response.json();

            // Agregar respuestas del bot (puede ser multiples burbujas)
            if (data.burbujas && data.burbujas.length > 1) {
                // Multiples burbujas con delay natural entre cada una
                for (let i = 0; i < data.burbujas.length; i++) {
                    if (i > 0) {
                        // Mostrar typing antes de cada burbuja adicional
                        showTyping();
                        // Delay mas largo y natural (1.5s - 3s)
                        const delay = Math.min(3000, Math.max(1500, data.burbujas[i].length * 30));
                        await new Promise(resolve => setTimeout(resolve, delay));
                        hideTyping();
                    }
                    // Solo mostrar productos en la ultima burbuja si es la primera
                    const productos = (i === 0) ? data.productos : null;
                    addMessage('bot', data.burbujas[i], productos);
                }
            } else {
                addMessage('bot', data.texto, data.productos);
            }

            saveSession();
        } catch (error) {
            hideTyping();
            console.error('Error enviando mensaje:', error);
            addMessage('bot', 'Lo siento, hubo un error. Por favor, intenta de nuevo.');
        }
    }

    function addMessage(type, text, productos = null) {
        // Si es respuesta del bot y hay que mostrar checkout
        const showCheckout = (type === 'bot' && state.showCheckoutOnNext);
        if (showCheckout) {
            state.showCheckoutOnNext = false; // Reset flag
        }
        
        const message = {
            type,
            text,
            productos,
            showCheckoutBtn: showCheckout,
            time: new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })
        };

        state.messages.push(message);
        renderMessage(message);
        scrollToBottom();
    }

    function renderMessages() {
        elements.messages.innerHTML = '';
        state.messages.forEach(msg => renderMessage(msg));
        scrollToBottom();
    }

    function renderMessage(message) {
        const div = document.createElement('div');
        div.className = `message message-${message.type}`;

        // Formatear texto
        const formattedText = formatText(message.text);

        let html = `
            <div class="message-bubble">${formattedText}</div>
            <div class="message-time">${message.time}</div>
        `;

        // Agregar productos si existen
        if (message.productos && message.productos.length > 0) {
            html += renderProductos(message.productos);
        }
        
        // Mostrar botón de finalizar compra si hay items en el carrito
        if (message.showCheckoutBtn && state.cart.length > 0) {
            html += `<button class="checkout-btn">Finalizar compra</button>`;
        }
        
        // Agregar checkout si existe
        if (message.checkoutHtml) {
            html += message.checkoutHtml;
        }

        div.innerHTML = html;
        elements.messages.appendChild(div);

        // Event listeners para botones de productos
        div.querySelectorAll('.product-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const productId = btn.dataset.productId;
                const productName = btn.dataset.productName;
                const productPrice = parseFloat(btn.dataset.productPrice) || 0;
                
                // Agregar al carrito
                addToCart(productId, productName, productPrice);
                
                // Marcar que debe mostrar botón de checkout en la próxima respuesta
                state.showCheckoutOnNext = true;
                
                // Enviar mensaje
                elements.input.value = `Quiero agregar ${productName} al carrito`;
                sendMessage();
            });
        });
        
        // Event listeners para botón de finalizar compra
        div.querySelectorAll('.checkout-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                finalizarCompra();
            });
        });
    }
    
    function addToCart(id, nombre, precio) {
        // Verificar si ya existe en el carrito
        const existente = state.cart.find(item => item.id === id);
        if (existente) {
            existente.cantidad++;
        } else {
            state.cart.push({ id, nombre, precio, cantidad: 1 });
        }
        updateCartButton();
    }
    
    function updateCartButton() {
        // Actualizar badge del carrito si existe
        const cartBadge = document.getElementById('cart-count');
        if (cartBadge) {
            const totalItems = state.cart.reduce((sum, item) => sum + item.cantidad, 0);
            cartBadge.textContent = totalItems;
            cartBadge.style.display = totalItems > 0 ? 'flex' : 'none';
        }
    }
    
    function finalizarCompra() {
        if (state.cart.length === 0) {
            elements.input.value = 'Quiero ver productos';
            sendMessage();
            return;
        }
        
        const total = state.cart.reduce((sum, item) => sum + (item.precio * item.cantidad), 0);
        const items = state.cart.map(item => `${item.nombre} (x${item.cantidad})`).join(', ');
        
        // Generar código de pedido
        const codigoPedido = 'RST' + Date.now().toString(36).toUpperCase();
        
        // Mostrar resumen y link de checkout
        const resumenHtml = `
            <div class="checkout-summary">
                <h4>Resumen de tu pedido</h4>
                <div class="checkout-items">
                    ${state.cart.map(item => `
                        <div class="checkout-item">
                            <span>${item.nombre} x${item.cantidad}</span>
                            <span>S/${(item.precio * item.cantidad).toFixed(2)}</span>
                        </div>
                    `).join('')}
                </div>
                <div class="checkout-total">
                    <strong>Total:</strong> S/${total.toFixed(2)}
                </div>
                <a href="https://rosatel.pe/checkout?codigo=${codigoPedido}" target="_blank" class="checkout-link-btn">
                    Completar pedido en Rosatel.pe
                </a>
                <p class="checkout-note">Código: ${codigoPedido}</p>
            </div>
        `;
        
        // Agregar mensaje de checkout
        renderMessage({
            sender: 'bot',
            text: '¡Perfecto! Aquí tienes el resumen de tu pedido:',
            time: new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' }),
            isCheckout: true,
            checkoutHtml: resumenHtml
        });
        
        // Limpiar carrito
        state.cart = [];
        updateCartButton();
    }

    function renderProductos(productos) {
        if (!productos || productos.length === 0) return '';
        
        return `<div class="products-grid">${productos.map(p => `
            <div class="product-card">
                ${p.imagen ? `<img src="${p.imagen}" alt="${p.nombre}" class="product-image" onerror="this.src='https://via.placeholder.com/150x150?text=Rosatel'">` : ''}
                <div class="product-info">
                    <div class="product-name">${p.nombre}</div>
                    <div class="product-price">
                        ${p.precio}
                        ${p.precio_original ? `<span class="product-price-original">${p.precio_original}</span>` : ''}
                        ${p.descuento ? `<span class="product-discount">-${Math.round(p.descuento * 100)}%</span>` : ''}
                    </div>
                    <button class="product-btn" data-product-id="${p.id}" data-product-name="${p.nombre}" data-product-price="${p.precio_num || 0}">
                        Lo quiero
                    </button>
                </div>
            </div>
        `).join('')}</div>`;
    }

    function formatText(text) {
        if (!text) return '';

        // Escapar HTML
        text = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');

        // Negritas: **texto** o *texto*
        text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/\*(.+?)\*/g, '<strong>$1</strong>');

        // Tachado: ~~texto~~
        text = text.replace(/~~(.+?)~~/g, '<del>$1</del>');

        // Saltos de linea
        text = text.replace(/\n/g, '<br>');

        // Links
        text = text.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank">$1</a>');

        return text;
    }

    function showTyping() {
        state.isTyping = true;

        const typingDiv = document.createElement('div');
        typingDiv.className = 'message message-bot';
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = `
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;

        elements.messages.appendChild(typingDiv);
        scrollToBottom();
    }

    function hideTyping() {
        state.isTyping = false;
        const typingDiv = document.getElementById('typing-indicator');
        if (typingDiv) {
            typingDiv.remove();
        }
    }

    function scrollToBottom() {
        setTimeout(() => {
            elements.messages.scrollTop = elements.messages.scrollHeight;
        }, 100);
    }

    // Exponer funciones globalmente para debugging
    window.RosatelWidget = {
        state,
        toggleWidget,
        sendMessage,
        clearSession: () => {
            localStorage.removeItem('rosatel_session');
            state.sessionId = null;
            state.messages = [];
            elements.messages.innerHTML = '';
            iniciarChat();
        }
    };

})();
