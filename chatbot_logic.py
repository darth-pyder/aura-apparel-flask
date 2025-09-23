# --- START OF FINAL, CORRECTED chatbot_logic.py ---

import os
import re
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import psycopg2
import psycopg2.extras

# --- 1. SETUP (Unchanged) ---
load_dotenv()
if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("CRITICAL: GOOGLE_API_KEY not found in .env file.")

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}
model = genai.GenerativeModel('gemini-1.5-flash-latest', safety_settings=safety_settings)

# --- 2. DATABASE TOOLS (Completely Rewritten for Robustness) ---
def get_db_connection(db_url):
    """Establishes a secure connection to the PostgreSQL database."""
    conn = psycopg2.connect(db_url)
    return conn

def find_bestsellers(db_url):
    conn = get_db_connection(db_url)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM products WHERE num_ratings > 0 ORDER BY rating DESC, num_ratings DESC LIMIT 3")
    bestsellers = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in bestsellers]

def find_reviews_for_product(db_url, search_term):
    conn = get_db_connection(db_url)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    clean_search = re.sub(r'reviews for|people say about|thoughts on', '', search_term, flags=re.IGNORECASE).strip()
    words = [word for word in clean_search.split() if word.lower() not in {'the', 'a', 'an'}]
    if not words:
        cursor.close()
        conn.close()
        return []
    
    conditions = " AND ".join(["p.name ILIKE %s"] * len(words))
    params = [f"%{word}%" for word in words]
    
    query = f"SELECT r.rating, r.comment, p.name FROM reviews r JOIN products p ON r.product_id = p.id WHERE {conditions} ORDER BY r.rating DESC LIMIT 3"
    cursor.execute(query, tuple(params))
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in reviews]

def find_relevant_products(db_url, search_term):
    conn = get_db_connection(db_url)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    query_lower = search_term.lower()
    
    # Check for price-based queries first
    price_match = re.search(r'(\d+)', query_lower)
    if price_match:
        price_limit = int(price_match.group(1))
        operator = "<"
        if any(word in query_lower for word in ['above', 'over', 'more than']):
            operator = ">"
        
        # This is the sale price calculation
        price_formula = "(original_price * (1 - discount_percent / 100.0))"
        query = f"SELECT * FROM products WHERE {price_formula} {operator} %s ORDER BY {price_formula} DESC LIMIT 3"
        cursor.execute(query, (price_limit,))
    else:
        # If not a price query, perform a text search
        normalized_term = re.sub(r't-?shirts?', 't-shirt', query_lower)
        stop_words = {'a', 'some', 'your', 'me', 'about', 'do', 'have', 'any', 'show', 'find', 'get', 'for', 'i', 'am', 'looking'}
        words = [word for word in normalized_term.split() if word not in stop_words]
        
        if not words:
            cursor.close()
            conn.close()
            return []
            
        conditions = " AND ".join(["(name ILIKE %s OR brand ILIKE %s OR category ILIKE %s)"] * len(words))
        params = [f"%{word.rstrip('s')}%" for word in words for _ in range(3)]
        
        query = f"SELECT * FROM products WHERE {conditions} ORDER BY num_ratings DESC, rating DESC LIMIT 3"
        cursor.execute(query, tuple(params))

    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in products]

def get_user_order_history(db_url, user_id):
    if user_id is None:
        return {"text": "Please log in to see your order history."}
    conn = get_db_connection(db_url)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT o.id, o.order_date, p.image_url, p.name 
        FROM orders o 
        JOIN order_items oi ON o.id = oi.order_id 
        JOIN products p ON oi.product_id = p.id 
        WHERE o.user_id = %s 
        ORDER BY o.order_date DESC LIMIT 4
    """, (user_id,))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    if not orders:
        return {"text": "You have no past orders."}
    return {"text": "Here is your recent order history:", "orders": [dict(row) for row in orders]}

# --- 3. INTENT CLASSIFICATION (Unchanged but still essential) ---
def _get_user_intent(query):
    query_lower = query.lower()
    query_words = set(re.findall(r'\b\w+\b', query_lower))

    if 'bestseller' in query_words or 'top selling' in query_lower:
        return 'find_bestsellers'
    if 'review' in query_words or 'say about' in query_lower:
        return 'find_reviews'
    if 'order' in query_words or 'history' in query_words:
        return 'get_order_history'
    if 'return policy' in query_lower:
        return 'get_return_policy'
    if any(word in query_words for word in ["hello", "hi", "hey"]):
        return 'greeting'
    
    return 'find_product'

# --- 4. RAG LOGIC (Updated to use the new tools and AI prompt) ---
def get_rag_response(user_query, chat_history, user_id, db_url):
    response_payload = {"text": "", "products": [], "orders": []}
    intent = _get_user_intent(user_query)

    if intent == 'find_bestsellers':
        products = find_bestsellers(db_url)
        if products:
            response_payload["text"] = "Of course! Here are our current top-selling products:"
            response_payload["products"] = products
    elif intent == 'find_reviews':
        reviews = find_reviews_for_product(db_url, user_query)
        if reviews:
            product_name = reviews[0]['name']
            response_payload["text"] = f"Absolutely! Here are the top reviews for '{product_name}':\n" + "\n".join([f'- "{r["comment"]}" ({r["rating"]}/5 stars)' for r in reviews])
        else:
            response_payload["text"] = "I'm sorry, I couldn't find any reviews for that product."
    elif intent == 'get_order_history':
        response_payload.update(get_user_order_history(db_url, user_id))
    elif intent == 'get_return_policy':
        response_payload["text"] = "We have a 30-day return policy for unworn items. You can start a return from your 'My Orders' page once an order is delivered."
    elif intent == 'greeting':
        response_payload["text"] = "Hello! I'm Aura Assistant. How can I help you find products or check reviews?"
    elif intent == 'find_product':
        products = find_relevant_products(db_url, user_query)
        if products:
            response_payload["text"] = "Certainly! Here are some products I found for you:"
            response_payload["products"] = products
        else:
            # AI FALLBACK
            history_string = "\n".join([f"User: {msg['content']}" if msg['role'] == 'user' else f"Assistant: {msg['content']}" for msg in chat_history])
            prompt = f"""You are "Aura Assistant," an AI shopping assistant for AURA Apparel, an Indian sustainable menswear brand (currency is Rupees, ₹). The user asked "{user_query}", but our database found no matching products. Provide a helpful, conversational response.

**Rules:**
- **DO NOT make up products.**
- If the question is about style (e.g., "tell me about your jeans"), give a creative, brand-focused answer in 2-4 sentences.
- If the question is off-topic (e.g., about the weather), you MUST politely say "I can only provide information about our products, reviews, and your orders."

CONVERSATION HISTORY:
---
{history_string}
---

AURA ASSISTANT (Concise, helpful response):"""
            try:
                response = model.generate_content(prompt)
                response_payload["text"] = response.text
            except Exception as e:
                print(f"Error during AI fallback: {e}")
                response_payload["text"] = "I'm sorry, I'm not sure how to answer that."
    
    if response_payload.get("products"):
        response_payload["products"] = [
            {"id": p.get('id'), "name": p.get('name'), "image_url": p.get('image_url'), "sale_price": f"₹{float(p.get('original_price', 0)) * (1 - p.get('discount_percent', 0) / 100.0):.0f}"}
            for p in response_payload["products"]
        ]
    return response_payload

# --- END OF FINAL, CORRECTED chatbot_logic.py ---