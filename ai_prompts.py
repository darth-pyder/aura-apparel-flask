# In a real application, you would use a library like `google-generativeai`
# and call an actual AI model. For this example, we'll simulate the AI's output.
import random

# NEW FUNCTION


def generate_content(prompt_type, context=None):
    """
    Simulates an AI model generating content based on a prompt type.
    """
    if prompt_type == "navigation_links":
        return [
            {"name": "Tops", "url": "/products?category=Tops"},
            {"name": "Bottoms", "url": "/products?category=Bottoms"},
            {"name": "Outerwear", "url": "/products?category=Outerwear"},
            {"name": "Activewear", "url": "/products?category=Activewear"},
            {"name": "All Products", "url": "/products"}
        ]

    if prompt_type == "hero_section":
        # ... (no change to this part)
        return {
            "headline": "Style Meets Sustainability",
            "offer": "Discover our new collection of eco-friendly apparel. Get 20% off your first order.",
            "cta_primary": "Shop All Products",
            "cta_secondary": "Learn More"
        }

    if prompt_type == "trust_content":
        # ... (no change to this part)
        return {
            "title": "Why Choose Us?",
            "body": "We believe fashion should feel good and do good. From sourcing the finest organic cotton to partnering with ethical factories, we're committed to transparency and sustainability. Every piece you buy is a step towards a healthier planet."
        }

    if prompt_type == "featured_products":
        # This can be deprecated or used for the homepage specifically
        # For now, we'll query the database instead
        return []

    # NEW: AI-generated user reviews
    if prompt_type == "user_reviews":
        # The context would be the product name, e.g., "Organic Cotton Crewneck Tee"
        # The AI would generate reviews relevant to that product.
        reviews = [
            {"author": "Alex R.", "rating": 5, "comment": "This is the softest t-shirt I've ever owned. The quality is incredible for the price. I'm buying one in every color!"},
            {"author": "Jessica M.", "rating": 5, "comment": "Finally, a perfect fit! It's not too tight and not too loose. Washes well without shrinking. Highly recommend."},
            {"author": "David Chen", "rating": 4, "comment": "Great shirt, very comfortable. I wish it came in more colors, but the white is a classic. Good value."}
        ]
        random.shuffle(reviews) # Make it seem more dynamic
        return reviews
    
    

