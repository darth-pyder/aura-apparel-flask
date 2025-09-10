document.addEventListener('DOMContentLoaded', () => {
    const chatWidgetContainer = document.getElementById('chat-widget-container');
    if (!chatWidgetContainer) {
        return;
    }

    const socket = io();

    // Get all the new and old elements
    const chatToggleButton = document.getElementById('chat-toggle-button');
    const chatMinimizeButton = document.getElementById('chat-minimize-button');
    const chatWidget = document.getElementById('chat-widget');
    const chatMessages = document.getElementById('chat-messages');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const suggestedRepliesContainer = document.getElementById('suggested-replies');

    // --- Event Listeners ---
    chatToggleButton.addEventListener('click', toggleChatVisibility);
    chatMinimizeButton.addEventListener('click', toggleChatVisibility);

    chatForm.addEventListener('submit', (event) => {
        event.preventDefault();
        sendMessage();
    });
    
    // NEW: Handle clicks on suggested reply chips
    suggestedRepliesContainer.addEventListener('click', (event) => {
        if (event.target.classList.contains('suggestion-chip')) {
            const message = event.target.textContent;
            chatInput.value = message;
            sendMessage();
        }
    });

    // --- Socket.IO Listeners ---
    socket.on('connect', () => {
        console.log('Socket.IO connected successfully!');
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO disconnected.');
    });

    // --- THIS IS THE KEY FIX ---
    socket.on('bot_response', (response) => {
        // The data from the server is now a complex object.
        // We pass this entire object to our new render function.
        renderBotResponse(response.data);
        suggestedRepliesContainer.style.display = 'flex';
    });
    // --- END OF FIX ---

    // --- Helper Functions ---
    function sendMessage() {
        const message = chatInput.value.trim();
        if (message) {
            addUserMessage(message);
            socket.emit('user_message', { data: message });
            chatInput.value = '';
            suggestedRepliesContainer.style.display = 'none';
        }
    }

    function addUserMessage(text) {
        const li = document.createElement('li');
        li.className = 'user-message';
        li.textContent = text; 
        chatMessages.appendChild(li);
        scrollToBottom();
    }

    // --- THIS IS THE NEW, UPGRADED RENDER FUNCTION ---
    function renderBotResponse(data) {
        // Step 1: Render the main text message
        const li = document.createElement('li');
        li.className = 'bot-message';
        li.innerHTML = data.text.replace(/\n/g, '<br>'); // Use innerHTML to respect line breaks
        chatMessages.appendChild(li);

        // Step 2: If the data contains products, render them as cards
        if (data.products && data.products.length > 0) {
            data.products.forEach(product => {
                const productCard = document.createElement('li');
                productCard.className = 'bot-product-card-container';
                const imageUrl = `/static/images/products/${product.image_url}`;
                const productUrl = `/product/${product.id}`;

                productCard.innerHTML = `
                    <div class="bot-product-card">
                        <img src="${imageUrl}" alt="${product.name}" class="bot-product-image">
                        <div class="bot-product-info">
                            <a href="${productUrl}" target="_blank" class="bot-product-link">${product.name}</a>
                            <p class="bot-product-price">${product.sale_price}</p>
                        </div>
                    </div>
                `;
                chatMessages.appendChild(productCard);
            });
        }
        
        // --- THIS IS THE NEW LOGIC for the Order History Grid ---
        if (data.orders && data.orders.length > 0) {
            const orderGrid = document.createElement('li');
            orderGrid.className = 'bot-order-grid-container';
            
            data.orders.forEach(order => {
                const imageUrl = `/static/images/products/${order.image_url}`;
                // In a real app, this would link to the order details page
                const orderUrl = `/order/${order.id}`;

                const orderCell = document.createElement('a');
                orderCell.href = orderUrl;
                orderCell.target = '_blank';
                orderCell.className = 'bot-order-cell';
                orderCell.innerHTML = `
                    <img src="${imageUrl}" alt="${order.name}" class="bot-order-image">
                    <div class="bot-order-info">
                        <strong>Order #${order.id}</strong>
                        <span>${order.order_date.split(' ')[0]}</span>
                    </div>
                `;
                orderGrid.appendChild(orderCell);
            });
            chatMessages.appendChild(orderGrid);
        }
        // --- END OF NEW LOGIC ---
        
        scrollToBottom();
    }

    function scrollToBottom() {
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 0);
    }

    function toggleChatVisibility() {
        chatWidget.classList.toggle('open');
        // This is a cleaner way to handle the toggle button's visibility
        const isChatOpen = chatWidget.classList.contains('open');
        chatToggleButton.style.transform = isChatOpen ? 'scale(0)' : 'scale(1)';
        chatToggleButton.style.opacity = isChatOpen ? '0' : '1';
    }

    function addMessage(text, className) {
        const li = document.createElement('li');
        li.className = className;
        li.textContent = text; 
        chatMessages.appendChild(li);
        
        // By wrapping the scroll command in a setTimeout of 0,
        // we push it to the end of the execution queue. This gives the browser
        // a moment to render the new message and update the scrollHeight
        // before we try to scroll.
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 0);
    }
    // --- END OF FIX ---
});