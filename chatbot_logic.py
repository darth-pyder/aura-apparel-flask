import os
import re
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import psycopg2
import psycopg2.extras

# --- 1. SETUP ---
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

# --- 2. DATABASE TOOLS (Corrected for PostgreSQL) ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database from the environment variable."""
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    return conn

def find_bestsellers():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM products WHERE num_ratings > 0 ORDER BY rating DESC, num_ratings DESC LIMIT 3")
    bestsellers = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in bestsellers]

def find_reviews_for_product(search_term):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    clean_search = re.sub(r'reviews for|people say about|thoughts on', '', search_term, flags=re.IGNORECASE).strip()
    words = [word for word in clean_search.split() if word not in {'the', 'a', 'an'}]
    if not words:
        cursor.close()
        conn.close()
        return []
    conditions = " AND ".join(["p.name ILIKE %s"] * len(words))
    params = [f"%{word.rstrip('s')}%" for word in words]
    query = f"SELECT r.rating, r.comment, p.name FROM reviews r JOIN products p ON r.product_id = p.id WHERE {conditions} ORDER BY r.rating DESC LIMIT 3"
    cursor.execute(query, tuple(params))
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in reviews]

def find_relevant_products(search_term):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    normalized_term = re.sub(r't-?shirts?', 't-shirt', search_term.lower())
    words = [word for word in normalized_term.split() if word not in {'a', 'some', 'your', 'me', 'about', 'do', 'have', 'any', 'show', 'find', 'get', 'for'}]
    if not words:
        cursor.close()
        conn.close()
        return []
    conditions = " AND ".join(["(name ILIKE %s OR brand ILIKE %s OR category ILIKE %s)"] * len(words))
    params = []
    for word in words:
        param = f"%{word.rstrip('s')}%"
        params.extend([param, param, param])
    query = f"SELECT * FROM products WHERE {conditions} ORDER BY num_ratings DESC, rating DESC LIMIT 3"
    cursor.execute(query, tuple(params))
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in products]

def get_user_order_history(user_id):
    if user_id is None:
        return {"text": "Please log in to see your order history."}
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT o.id, o.order_date, p.image_url, p.name 
        FROM orders o 
        JOIN order_items oi ON o.id = oi.order_id 
        JOIN products p ON oi.product_id = p.id 
        WHERE o.user_id = %s 
        GROUP BY o.id, p.image_url, p.name 
        ORDER BY o.order_date DESC LIMIT 4
    """, (user_id,))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    if not orders:
        return {"text": "You have no past orders."}
    return {"text": "Here is your recent order history:", "orders": [dict(row) for row in orders]}

# --- 3. DEFINITIVE RAG LOGIC (TOOL-FIRST ARCHITECTURE) ---
def get_rag_response(user_query, chat_history, user_id):
    response_payload = {"text": "", "products": []}
    
    # Step 1: Check for high-priority, non-search keywords
    if "bestseller" in user_query.lower():
        products = find_bestsellers()
        if products:
            response_payload["text"] = "Of course! Here are our current top-selling products:"
            response_payload["products"] = products
    elif "review" in user_query.lower() or "say about" in user_query.lower():
        reviews = find_reviews_for_product(user_query)
        if reviews:
            product_name = reviews[0]['name']
            response_payload["text"] = f"Absolutely! Here are the top reviews for '{product_name}':\n" + "\n".join([f'- "{r["comment"]}" ({r["rating"]}/5 stars)' for r in reviews])
        else:
            response_payload["text"] = "I'm sorry, I couldn't find any reviews for that."
    elif "order" in user_query.lower():
        response_payload.update(get_user_order_history(user_id))
    elif "return policy" in user_query.lower():
        response_payload["text"] = "We have a 30-day return policy for unworn items. You can start a return from your 'My Orders' page once an order is delivered."
    elif any(word in user_query.lower() for word in ["hello", "hi", "hey"]):
        response_payload["text"] = "Hello! I'm Aura Assistant. How can I help you find products or check reviews?"
    else:
        # Step 2: If no keyword, perform a product search
        products = find_relevant_products(user_query)
        if products:
            response_payload["text"] = "Certainly! Here are some products I found for you:"
            response_payload["products"] = products
        else:
            # Step 3: FALLBACK TO AI (Only if all database searches fail)
            history_string = "\n".join([f"User: {msg['content']}" if msg['role'] == 'user' else f"Assistant: {msg['content']}" for msg in chat_history])
            prompt = f"""You are "Aura Assistant," a helpful and direct AI shopping assistant. The user asked a question ("{user_query}"), but our database found no matching products. Your job is to provide a helpful, conversational response.

**Rules:**
- **DO NOT make up products.**
- If the user asks a question you can't answer (e.g., about the weather), you MUST politely say "I can only provide information about our products, reviews, and your orders."
- For other general questions (e.g., "tell me about your jeans"), you can give a creative, brand-focused answer in 2-4 sentences.

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

    # Step 4: FORMAT PRODUCT CARDS for UI
    if response_payload.get("products"):
        response_payload["products"] = [
            {"id": p.get('id'), "name": p.get('name'), "image_url": p.get('image_url'), "sale_price": f"₹{float(p.get('original_price', 0)) * (1 - p.get('discount_percent', 0) / 100.0):.0f}"}
            for p in response_payload["products"]
        ]
    
    return response_payload