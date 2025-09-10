// static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const quickViewModal = document.getElementById('quickViewModal');
    if (quickViewModal) {
        quickViewModal.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            const productId = button.getAttribute('data-product-id');
            const modalBody = document.getElementById('quickViewModalBody');
            
            // Show a loading spinner
            modalBody.innerHTML = '<div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div>';

            // Fetch the quick view content from our new Flask route
            fetch(`/quick_view/${productId}`)
                .then(response => response.text())
                .then(html => {
                    modalBody.innerHTML = html;
                })
                .catch(error => {
                    modalBody.innerHTML = 'Failed to load product details.';
                    console.error('Error:', error);
                });
        });
        const allFlashMessages = document.querySelectorAll('.flash');

        allFlashMessages.forEach(flashMessage => {
            const closeButton = flashMessage.querySelector('.flash-close');
            
            // Function to dismiss the message
            const dismissMessage = () => {
                flashMessage.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                flashMessage.style.opacity = '0';
                flashMessage.style.transform = 'translateY(-20px)';
                setTimeout(() => flashMessage.remove(), 300);
            };

            // Dismiss when the close button is clicked
            if (closeButton) {
                closeButton.addEventListener('click', dismissMessage);
            }

            // Automatically dismiss after 5 seconds
            setTimeout(dismissMessage, 5000);
        });
    }
    // --- THIS IS THE NEW CODE YOU NEED TO ADD ---
    // --- Initialize Product Carousel ---
    const productCarousel = new Swiper('.product-carousel', {
        // Optional parameters
        loop: true,
        slidesPerView: 4, // Show 4 slides on desktop
        spaceBetween: 30, // Space between slides
        
        // Navigation arrows
        navigation: {
          nextEl: '.swiper-button-next',
          prevEl: '.swiper-button-prev',
        },
        
        // Responsive breakpoints
        breakpoints: {
          // when window width is >= 320px
          320: {
            slidesPerView: 1,
            spaceBetween: 10
          },
          // when window width is >= 576px
          576: {
            slidesPerView: 2,
            spaceBetween: 20
          },
          // when window width is >= 992px
          992: {
            slidesPerView: 4,
            spaceBetween: 30
          }
        }
    });
    // --- END OF NEW CODE ---

    // --- NEW: Size Selection Logic ---
    const sizeSelector = document.getElementById('size-selector');
    const selectedInventoryIdInput = document.getElementById('selected-inventory-id');
    const addToCartForm = document.getElementById('add-to-cart-form');
    const sizeError = document.getElementById('size-error');

    if (sizeSelector && selectedInventoryIdInput && addToCartForm) {
        // Handle clicking on a size button
        sizeSelector.addEventListener('click', (event) => {
            if (event.target.tagName === 'BUTTON') {
                // Clear the 'selected' class from all buttons
                document.querySelectorAll('.size-btn').forEach(btn => btn.classList.remove('selected'));
                
                // Add 'selected' to the clicked button
                event.target.classList.add('selected');
                
                // Update the hidden input with the inventory ID
                selectedInventoryIdInput.value = event.target.dataset.inventoryId;
                sizeError.style.display = 'none'; // Hide error message
            }
        });

        // Validate that a size is selected before submitting
        addToCartForm.addEventListener('submit', (event) => {
            if (!selectedInventoryIdInput.value) {
                event.preventDefault(); // Stop the form submission
                sizeError.style.display = 'block'; // Show error message
            }
        });
    }
    // --- END OF NEW LOGIC ---

    // --- NEW LIVE SEARCH LOGIC ---
    // --- DEFINITIVE FINAL SEARCH PANEL LOGIC ---
    const searchPanel = document.getElementById('search-panel');
    const searchTriggerBtn = document.getElementById('search-panel-trigger');
    const panelSearchInput = document.getElementById('panel-search-input');
    const panelSearchResults = document.getElementById('panel-search-results');

    if (searchPanel && searchTriggerBtn) {
        const toggleSearchPanel = () => {
            const isOpen = searchPanel.classList.toggle('open');
            searchTriggerBtn.classList.toggle('is-active', isOpen);
            if (isOpen) {
                setTimeout(() => panelSearchInput.focus(), 300);
            }
        };
        searchTriggerBtn.addEventListener('click', toggleSearchPanel);

        // Close with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && searchPanel.classList.contains('open')) {
                toggleSearchPanel();
            }
        });

        // --- Live Search Logic ---
        const debounce = (func, delay) => {
            let timeoutId;
            return (...args) => {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => { func.apply(this, args); }, delay);
            };
        };

        const performSearch = debounce((query) => {
            if (query.length < 2) {
                panelSearchResults.innerHTML = '';
                panelSearchResults.style.display = 'none';
                return;
            }
            fetch(`/live_search?q=${query}`)
                .then(response => response.json())
                .then(data => {
                    panelSearchResults.innerHTML = '';
                    if (data.products && data.products.length > 0) {
                        data.products.forEach(product => {
                            const resultItem = document.createElement('a');
                            resultItem.href = `/product/${product.id}`;
                            resultItem.className = 'search-result-item';
                            resultItem.innerHTML = `
                                <img src="/static/images/products/${product.image_url}" alt="${product.name}">
                                <div class="search-result-info">
                                    <span class="brand">${product.brand}</span>
                                    <span class="name">${product.name}</span>
                                </div>
                                <span class="price">${product.sale_price}</span>
                            `;
                            panelSearchResults.appendChild(resultItem);
                        });
                        panelSearchResults.style.display = 'block';
                    } else {
                        panelSearchResults.innerHTML = '<div class="no-results">No products found.</div>';
                        panelSearchResults.style.display = 'block';
                    }
                });
        }, 250);

        panelSearchInput.addEventListener('input', () => {
            performSearch(panelSearchInput.value);
        });
    }
});