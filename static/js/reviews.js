// static/js/reviews.js
document.addEventListener('DOMContentLoaded', () => {
    const loadMoreBtn = document.getElementById('load-more-reviews');

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => {
            const productId = loadMoreBtn.dataset.productId;
            let nextPage = parseInt(loadMoreBtn.dataset.nextPage);
            const sortBy = loadMoreBtn.dataset.sort;

            // Fetch the next page of reviews from our new route
            fetch(`/get_reviews/${productId}?page=${nextPage}&sort=${sortBy}`)
                .then(response => response.json())
                .then(data => {
                    if (data.reviews.length > 0) {
                        const reviewsList = document.getElementById('reviews-list');
                        data.reviews.forEach(review => {
                            // Create the HTML for a new review card
                            const reviewCard = document.createElement('div');
                            reviewCard.className = 'review-card';
                            
                            let ratingClass = 'rating-neutral';
                            if (review.rating >= 4) ratingClass = 'rating-good';
                            if (review.rating < 3) ratingClass = 'rating-bad';

                            reviewCard.innerHTML = `
                                <div class="review-header">
                                    <strong>${review.username}</strong>
                                    <div class="review-rating">
                                        <span class="${ratingClass}">${review.rating} ★</span>
                                    </div>
                                </div>
                                <p class="review-comment">"${review.comment}"</p>
                            `;
                            reviewsList.appendChild(reviewCard);
                        });
                        // Increment the page number for the next click
                        loadMoreBtn.dataset.nextPage = nextPage + 1;
                    } else {
                        // If no more reviews are returned, hide the button
                        loadMoreBtn.textContent = 'No More Reviews';
                        loadMoreBtn.disabled = true;
                    }
                });
        });
    }
});