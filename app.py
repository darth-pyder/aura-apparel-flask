import sqlite3
import os
import random
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, g, request, redirect, url_for, flash, session, jsonify
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Import your custom modules
from chatbot_logic import get_rag_response
from ai_prompts import generate_content

# --- 1. APP SETUP & CONFIGURATION ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-super-secret-key-that-you-should-change'
socketio = SocketIO(app)
DATABASE = 'products.db'
REVIEWS_PER_PAGE = 4

PLATFORM_FEE = 20
FREE_SHIPPING_THRESHOLD = 1499
DELIVERY_CHARGE = 50


# --- Login Manager Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 
login_manager.login_message_category = "info"

class User(UserMixin):
    # MODIFIED: Added first_name to the constructor
    def __init__(self, id, username, email, password_hash, first_name):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.first_name = first_name # NEW: Store the user's first name

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user_data = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user_data:
        # MODIFIED: Pass the first_name when creating the User object
        return User(id=user_data['id'], 
                    username=user_data['username'], 
                    email=user_data['email'], 
                    password_hash=user_data['password_hash'],
                    first_name=user_data['first_name'])
    return None

# ---- Database Connection Handling (No changes) ----
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def process_products(products_data):
    """Helper function to calculate sale price for a list of products."""
    processed = []
    for product in products_data:
        # Convert the database row to a mutable dictionary
        p = dict(product)
        # Calculate the sale price and add it to the dictionary
        p['sale_price'] = p['original_price'] * (1 - p['discount_percent'] / 100.0)
        processed.append(p)
    return processed

# ---- NEW: Add a Context Processor ----
# This makes the cart contents available to ALL templates automatically.
@app.context_processor
def inject_global_variables():
    """
    Makes variables globally available to all templates.
    This is the definitive fix for the 'product is undefined' error.
    """
    # Handle the cart item count
    cart_items = session.get('cart', {})
    item_count = sum(cart_items.values())
    
    # Handle the 'product' variable
    # This ensures a 'product' object is ALWAYS available, even if it's None.
    # On the product detail page, the real product data will overwrite this.
    # On all other pages, it will exist as None, preventing the error.
    return dict(
        cart_item_count=item_count,
        product=None 
    )



# ---- Main Routes ----
@app.route('/')
def home():
    db = get_db()
    featured_products_data = db.execute("SELECT * FROM products ORDER BY rating DESC LIMIT 8").fetchall()
    featured_products = process_products(featured_products_data) # <-- Use the new function
    navigation_links = generate_content("navigation_links")
    hero_content = generate_content("hero_section")
    trust_content = generate_content("trust_content") # <-- ADD THIS LINE BACK

    return render_template(
        'index.html',
        navigation_links=navigation_links,
        hero=hero_content,
        trust=trust_content, # <-- AND PASS IT IN HERE
        products=featured_products
    )

# ... (all your other routes) ...

# NEW ROUTE FOR THE FEATURED COLLECTION
@app.route('/collection/desert-wanderer')
def desert_wanderer_collection():
    db = get_db()
    
    # Define which product IDs belong to this collection
    # These are items like linen shirts, chinos, shorts, etc.
    collection_ids = [18, 24, 25, 31, 37] # IDs for linen shirt, chinos, shorts, leather jacket
    
    # Create the correct number of placeholders for the SQL query
    placeholders = ','.join('?' for _ in collection_ids)
    
    # Fetch the products from the database
    collection_products_data = db.execute(
        f"SELECT * FROM products WHERE id IN ({placeholders})", 
        collection_ids
    ).fetchall()
    
    # Process the products to calculate sale prices
    products = process_products(collection_products_data)
    
    navigation_links = generate_content("navigation_links")
    filter_brands = [row['brand'] for row in db.execute("SELECT DISTINCT brand FROM products ORDER BY brand").fetchall()]
    
    # We reuse the products.html template to display the collection
    return render_template(
        'products.html',
        navigation_links=navigation_links,
        products=products,
        filter_brands=filter_brands,
        # Pass a special title for this page
        collection_title="The Desert Wanderer Collection",
        # Pass empty/default filters so the sidebar doesn't crash
        active_filters={'category': None, 'brand': None, 'price': None, 'rating': None},
        search_query=None,
        sort_by='name_asc'
    )

@app.route('/products')
def product_listing():
    db = get_db()
    
    # Get all filter/search parameters from the URL
    category = request.args.get('category')
    brand = request.args.get('brand')
    search_query = request.args.get('q')
    price_range = request.args.get('price')
    rating = request.args.get('rating')
    sort_by = request.args.get('sort', 'relevance') # Default sort to relevance

    # --- THIS IS THE NEW, SMARTER SEARCH LOGIC ---
    base_query = "SELECT *, (original_price * (1 - discount_percent / 100.0)) as sale_price"
    score_clauses = []
    params = []
    conditions = []

    if search_query:
        search_words = search_query.lower().split()
        for word in search_words:
            # Handle plural vs singular by removing 's' if it exists
            singular_word = word.rstrip('s')
            param = f"%{singular_word}%"
            score_clauses.append("(CASE WHEN name LIKE ? THEN 10 ELSE 0 END)")
            score_clauses.append("(CASE WHEN brand LIKE ? THEN 5 ELSE 0 END)")
            score_clauses.append("(CASE WHEN description LIKE ? THEN 1 ELSE 0 END)")
            params.extend([param, param, param])
        relevance_score_sql = " + ".join(score_clauses)
        base_query += f", ({relevance_score_sql}) as relevance_score"
        conditions.append("relevance_score > 0")

    query = f"{base_query} FROM products"
    # --- END OF NEW SEARCH LOGIC ---

    if category: conditions.append("category = ?"); params.append(category)
    if brand: conditions.append("brand = ?"); params.append(brand)
    if rating: conditions.append("rating >= ?"); params.append(float(rating))
    
    if price_range:
        # We need to add the sale_price calculation to the subquery for filtering
        low, high = price_range.split('-')
        conditions.append("(original_price * (1 - discount_percent / 100.0)) BETWEEN ? AND ?")
        params.extend([int(low), int(high)])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    # Sorting logic
    if sort_by == 'price_asc': query += " ORDER BY sale_price ASC"
    elif sort_by == 'price_desc': query += " ORDER BY sale_price DESC"
    elif sort_by == 'rating_desc': query += " ORDER BY rating DESC"
    elif search_query: query += " ORDER BY relevance_score DESC" # Prioritize relevance if searching
    else: query += " ORDER BY name ASC"

    all_products_data = db.execute(query, params).fetchall()
    
    navigation_links = generate_content("navigation_links")
    filter_brands = [row['brand'] for row in db.execute("SELECT DISTINCT brand FROM products ORDER BY brand").fetchall()]

    return render_template(
        'products.html', 
        navigation_links=navigation_links, 
        products=all_products_data,
        filter_brands=filter_brands,
        active_filters={'category': category, 'brand': brand, 'price': price_range, 'rating': rating},
        search_query=search_query, 
        sort_by=sort_by,
        collection_title=None # Ensure this is defined
    )

REVIEWS_PER_PAGE = 4

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    db = get_db()
    product_data = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product_data: return "Product not found", 404
    
    product = process_products([product_data])[0]
    
    # --- NEW: Fetch inventory for this product ---
    inventory = db.execute(
        "SELECT id, size, stock_quantity FROM inventory WHERE product_id = ? ORDER BY size",
        (product_id,)
    ).fetchall()

    # --- THIS IS THE KEY CHANGE for sorting and initial load ---
    sort_by = request.args.get('sort_reviews', 'newest')
    order_clause = "ORDER BY r.review_date DESC" # Default
    if sort_by == 'oldest': order_clause = "ORDER BY r.review_date ASC"
    elif sort_by == 'highest': order_clause = "ORDER BY r.rating DESC, r.review_date DESC"
    elif sort_by == 'lowest': order_clause = "ORDER BY r.rating ASC, r.review_date DESC"

    reviews = db.execute(f"""
        SELECT r.rating, r.comment, u.username 
        FROM reviews r JOIN users u ON r.user_id = u.id 
        WHERE r.product_id = ? {order_clause} LIMIT ?
    """, (product_id, REVIEWS_PER_PAGE)).fetchall()
    
    # --- THIS IS THE NEW LOGIC ---
    # Fetch 4 other products from the same category to recommend
    recommended_products_data = db.execute(
        "SELECT * FROM products WHERE category = ? AND id != ? ORDER BY RANDOM() LIMIT 4",
        (product['category'], product_id)
    ).fetchall()
    recommended_products = process_products(recommended_products_data)
    # --- END OF NEW LOGIC ---

    cart = session.get('cart', {})
    is_in_cart = any(key.startswith(f"{product_id}-") for key in cart.keys())
    
    is_in_wishlist = False
    if current_user.is_authenticated:
        db = get_db() # Get the database connection
        is_in_wishlist_data = db.execute(
            "SELECT id FROM wishlist WHERE user_id = ? AND product_id = ?",
            (current_user.id, product_id)
        ).fetchone()
        if is_in_wishlist_data: is_in_wishlist = True

    navigation_links = generate_content("navigation_links")
    
    return render_template(
        'product_detail.html', 
        navigation_links=navigation_links, 
        product=product, 
        inventory=inventory,
        reviews=reviews,
        is_in_cart=is_in_cart,
        recommended_products=recommended_products, # <-- Pass the new data
        request=request,
        is_in_wishlist=is_in_wishlist,
        sort_by=sort_by
    )

@app.route('/quick_view/<int:product_id>')
def quick_view(product_id):
    db = get_db()
    product_data = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product_data:
        return jsonify(error="Product not found"), 404
    
    product = process_products([product_data])[0]
    
    # Render a small, partial HTML template with just the modal content
    return render_template('quick_view_content.html', product=product)

@app.route('/live_search')
def live_search():
    query = request.args.get('q', '')
    if not query or len(query) < 2:
        # Don't search if the query is too short
        return jsonify(products=[])

    db = get_db()
    
    # Use a smart, scored search similar to our chatbot
    search_words = query.lower().split()
    score_clauses = []
    params = []
    for word in search_words:
        param = f"%{word}%"
        score_clauses.append("(CASE WHEN name LIKE ? THEN 10 ELSE 0 END)")
        score_clauses.append("(CASE WHEN brand LIKE ? THEN 5 ELSE 0 END)")
        params.extend([param, param])

    relevance_score_sql = " + ".join(score_clauses)
    
    search_query = f"""
        SELECT *, ({relevance_score_sql}) as relevance_score
        FROM products
        WHERE relevance_score > 0
        ORDER BY relevance_score DESC, rating DESC
        LIMIT 5
    """
    
    products_data = db.execute(search_query, params).fetchall()
    products = process_products(products_data) # Calculate sale prices
    
    # Convert the database rows into a list of dictionaries to send as JSON
    results = [
        {
            "id": p['id'],
            "name": p['name'],
            "brand": p['brand'],
            "image_url": p['image_url'],
            "sale_price": f"₹{p['sale_price']:.0f}"
        }
        for p in products
    ]
    
    return jsonify(products=results)


@app.route('/about')
def about():
    navigation_links = generate_content("navigation_links")
    # This now points to our new, dedicated template
    return render_template('about_us.html', navigation_links=navigation_links)

@app.route('/contact')
def contact():
    navigation_links = generate_content("navigation_links")
    return render_template('static_page.html', navigation_links=navigation_links, title="Contact Us", content_key="contact")

@app.route('/privacy-policy')
def privacy_policy():
    navigation_links = generate_content("navigation_links")
    return render_template('static_page.html', navigation_links=navigation_links, title="Privacy Policy", content_key="privacy")

@app.route('/return-policy')
def return_policy():
    navigation_links = generate_content("navigation_links")
    return render_template('static_page.html', navigation_links=navigation_links, title="Return Policy", content_key="return")

@app.route('/faq')
def faq():
    navigation_links = generate_content("navigation_links")
    return render_template('static_page.html', navigation_links=navigation_links, title="Frequently Asked Questions", content_key="faq")

@app.route('/track-order', methods=['GET', 'POST'])
def track_order():
    navigation_links = generate_content("navigation_links")
    order_details = None
    
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        if order_id:
            db = get_db()
            # Try to find the order by its ID
            order_details = db.execute(
                "SELECT id, order_date, shipping_status, tracking_number FROM orders WHERE id = ?",
                (order_id,)
            ).fetchone()
            
            if order_details is None:
                flash(f"Order ID #{order_id} not found. Please check the number and try again.", "error")
        else:
            flash("Please enter an Order ID.", "error")

    return render_template('track_order.html', navigation_links=navigation_links, order_details=order_details)

@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, current_user.id)).fetchone()
    
    if order is None:
        flash("Order not found or you do not have permission to view it.", "error")
        return redirect(url_for('my_orders'))
        
    order_items_data = db.execute("""
        SELECT p.id as product_id, p.name, p.image_url, oi.quantity, oi.price as price_paid, oi.size
        FROM order_items oi JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    """, (order_id,)).fetchall()
    order_items = [dict(row) for row in order_items_data]

    # THE FIX for "Address Not Found": Fetch the specific address linked to the order
    shipping_address = db.execute("""
        SELECT * FROM addresses WHERE id = ?
    """, (order['shipping_address_id'],)).fetchone()

    subtotal = sum(item['price_paid'] * item['quantity'] for item in order_items)
    delivery_charge = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else DELIVERY_CHARGE
    platform_fee = PLATFORM_FEE
    
    # THE FIX for Date Formatting: Parse the date string into a Python datetime object
    order_date_obj = datetime.strptime(order['order_date'], "%Y-%m-%d %H:%M:%S")

    navigation_links = generate_content("navigation_links")
    
    return render_template('order_details.html', 
                           navigation_links=navigation_links, 
                           order=order,
                           order_items=order_items,
                           shipping_address=shipping_address,
                           subtotal=subtotal,
                           delivery_charge=delivery_charge,
                           platform_fee=platform_fee,
                           order_date=order_date_obj) # Pass the formatted date object

# ---- NEW: Authentication Routes ----
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        db = get_db()
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        # NEW: Get additional fields from the form
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form['phone']

        user_by_username = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        user_by_email = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user_by_username:
            flash('Username already exists. Please choose a different one.', 'error')
        elif user_by_email:
            flash('Email address already registered. Please log in.', 'error')
        else:
            password_hash = generate_password_hash(password)
            # MODIFIED: Insert statement now includes the new required fields
            db.execute("INSERT INTO users (username, email, password_hash, first_name, last_name, phone) VALUES (?, ?, ?, ?, ?, ?)", 
                       (username, email, password_hash, first_name, last_name, phone))
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))

    navigation_links = generate_content("navigation_links")
    return render_template('register.html', navigation_links=navigation_links)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_from_db = db_get_user(username)
        
        if user_from_db and check_password_hash(user_from_db.password_hash, password):
            login_user(user_from_db)
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'error')

    navigation_links = generate_content("navigation_links")
    return render_template('login.html', navigation_links=navigation_links)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))
    
def db_get_user(username):
    """Helper function to get user from DB."""
    db = get_db()
    user_data = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if user_data:
        # MODIFIED: Pass the first_name when creating the User object here as well
        return User(id=user_data['id'], 
                    username=user_data['username'], 
                    email=user_data['email'], 
                    password_hash=user_data['password_hash'],
                    first_name=user_data['first_name'])
    return None

@app.route('/my-orders')
@login_required
def my_orders():
    db = get_db()
    
    # Fetch all orders for the current user, newest first
    user_orders_data = db.execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY order_date DESC",
        (current_user.id,)
    ).fetchall()
    
    orders = []
    for order_data in user_orders_data:
        # For each order, fetch its associated items
        items_data = db.execute("""
            SELECT p.name, oi.quantity, oi.price, oi.id as order_item_id, oi.has_reviewed
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
        """, (order_data['id'],)).fetchall()
        
        orders.append({
            'id': order_data['id'],
            'date': order_data['order_date'],
            'total': order_data['total_price'],
            'status': order_data['status'],
            'shipping_status': order_data['shipping_status'], # <-- ADD THIS LINE
            'order_products': items_data
        })
        
    navigation_links = generate_content("navigation_links")
    # ... inside the /profile route ...
    return render_template('my_orders.html', navigation_links=navigation_links, orders=orders)

# NEW ROUTE for the account management page
@app.route('/account')
@login_required
def account():
    db = get_db()
    # Fetch the default address and the most recent order for the dashboard summary
    default_address = db.execute("SELECT * FROM addresses WHERE user_id = ? AND is_default = 1", (current_user.id,)).fetchone()
    last_order = db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY order_date DESC LIMIT 1", (current_user.id,)).fetchone()
    
    navigation_links = generate_content("navigation_links")
    return render_template('account_dashboard.html', 
                           navigation_links=navigation_links, 
                           default_address=default_address,
                           last_order=last_order)

# --- NEW: Route for the Profile & Security page ---
@app.route('/account/profile', methods=['GET', 'POST'])
@login_required
def account_profile():
    db = get_db()
    if request.method == 'POST':
        # Check which form was submitted
        if 'update_details' in request.form:
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            phone = request.form.get('phone')
            db.execute("UPDATE users SET first_name = ?, last_name = ?, phone = ? WHERE id = ?",
                       (first_name, last_name, phone, current_user.id))
            db.commit()
            flash('Your personal details have been updated.', 'success')
        
        elif 'change_password' in request.form:
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            user = db.execute("SELECT password_hash FROM users WHERE id = ?", (current_user.id,)).fetchone()

            if not check_password_hash(user['password_hash'], current_password):
                flash('Your current password does not match.', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match.', 'error')
            else:
                new_password_hash = generate_password_hash(new_password)
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, current_user.id))
                db.commit()
                flash('Your password has been changed successfully.', 'success')

        return redirect(url_for('account_profile'))

    user_data = db.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
    navigation_links = generate_content("navigation_links")
    return render_template('account_profile.html', navigation_links=navigation_links, user=user_data)

# --- NEW: Route for the Address Book page ---
@app.route('/account/addresses', methods=['GET', 'POST'])
@login_required
def account_addresses():
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add':
            db.execute("INSERT INTO addresses (user_id, address, city, state, zip_code) VALUES (?, ?, ?, ?, ?)",
                       (current_user.id, request.form.get('address'), request.form.get('city'), 
                        request.form.get('state'), request.form.get('zip_code')))
            flash('New address added.', 'success')

        elif action == 'delete':
            address_id = request.form.get('address_id')
            db.execute("DELETE FROM addresses WHERE id = ? AND user_id = ?", (address_id, current_user.id))
            flash('Address removed.', 'success')

        elif action == 'set_default':
            address_id = request.form.get('address_id')
            db.execute("UPDATE addresses SET is_default = 0 WHERE user_id = ?", (current_user.id,))
            db.execute("UPDATE addresses SET is_default = 1 WHERE id = ? AND user_id = ?", (address_id, current_user.id))
            flash('Default address updated.', 'success')
            
        db.commit()
        return redirect(url_for('account_addresses'))

    addresses = db.execute("SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC", (current_user.id,)).fetchall()
    navigation_links = generate_content("navigation_links")
    return render_template('account_addresses.html', navigation_links=navigation_links, addresses=addresses)


# ADD THIS ENTIRE NEW BLOCK of routes after your /account route
@app.route('/wishlist')
@login_required
def wishlist():
    db = get_db()
    wishlist_items_data = db.execute("SELECT p.* FROM products p JOIN wishlist w ON p.id = w.product_id WHERE w.user_id = ?", (current_user.id,)).fetchall()
    wishlist_items = process_products(wishlist_items_data)
    return render_template('wishlist.html', products=wishlist_items)

@app.route('/wishlist/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_wishlist(product_id):
    db = get_db()
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.execute("INSERT INTO wishlist (user_id, product_id, added_date) VALUES (?, ?, ?)", (current_user.id, product_id, current_time))
        db.commit()
        flash('Item added to your wishlist!', 'success')
    except sqlite3.IntegrityError:
        flash('This item is already in your wishlist.', 'info')
    return redirect(request.referrer)

@app.route('/wishlist/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_wishlist(product_id):
    db = get_db()
    db.execute("DELETE FROM wishlist WHERE user_id = ? AND product_id = ?", (current_user.id, product_id))
    db.commit()
    flash('Item removed from your wishlist.', 'success')
    return redirect(request.referrer)

@app.route('/leave_review/<int:order_item_id>')
@login_required
def leave_review(order_item_id):
    db = get_db()
    item = db.execute("""
        SELECT oi.id, oi.product_id, p.name FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN products p ON oi.product_id = p.id
        WHERE oi.id = ? AND o.user_id = ? AND oi.has_reviewed = 0
    """, (order_item_id, current_user.id)).fetchone()
    
    if item is None:
        flash("You are not eligible to review this item, or it has already been reviewed.", "error")
        # MODIFIED: Redirect to the correct 'my_orders' page
        return redirect(url_for('my_orders'))
        
    navigation_links = generate_content("navigation_links")
    return render_template('review.html', navigation_links=navigation_links, order_item_id=order_item_id, product=item)

@app.route('/submit_review/<int:order_item_id>', methods=['POST'])
@login_required
def submit_review(order_item_id):
    db = get_db()
    # Another security check to prevent double-reviews
    item = db.execute("""
        SELECT oi.id, oi.product_id FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        WHERE oi.id = ? AND o.user_id = ? AND oi.has_reviewed = 0
    """, (order_item_id, current_user.id)).fetchone()

    if item is None:
        flash("Review submission failed. The item may have already been reviewed.", "error")
        return redirect(url_for('my_orders'))
    
    rating = request.form['rating']
    comment = request.form['comment']
    product_id = item['product_id']
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Insert the new review into the 'reviews' table
    db.execute("INSERT INTO reviews (product_id, user_id, rating, comment, review_date) VALUES (?, ?, ?, ?, ?)",
               (product_id, current_user.id, rating, comment, current_time))
    
    # 2. Mark this specific order item as 'reviewed'
    db.execute("UPDATE order_items SET has_reviewed = 1 WHERE id = ?", (order_item_id,))
    
    # 3. Recalculate and update the product's overall average rating and number of ratings
    stats = db.execute("SELECT AVG(rating) as avg, COUNT(id) as count FROM reviews WHERE product_id = ?", (product_id,)).fetchone()
    if stats:
        db.execute("UPDATE products SET rating = ?, num_ratings = ? WHERE id = ?", 
                   (stats['avg'], stats['count'], product_id))
    
    db.commit()
    flash("Thank you for your review!", "success")
    # MODIFIED: Redirect to the 'my_orders' page where they can see the "Reviewed" status
    return redirect(url_for('my_orders'))

@app.route('/request_return/<int:order_id>', methods=['POST'], endpoint='request_return')
@login_required
def request_return(order_id):
    db = get_db()
    
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, current_user.id)
    ).fetchone()
    
    if order is None:
        flash("Order not found or access denied.", "error")
        # MODIFIED: Redirect to the correct 'my_orders' page
        return redirect(url_for('my_orders'))
        
    db.execute(
        "UPDATE orders SET status = 'Return Requested' WHERE id = ?",
        (order_id,)
    )
    db.commit()
    
    flash(f"Return requested for Order #{order_id}. You will be contacted shortly.", "success")
    # MODIFIED: Redirect to the 'my_orders' page to see the status update
    return redirect(url_for('my_orders'))

# ---- NEW: Shopping Cart Routes ----
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    cart = session.get('cart', {})
    quantity = int(request.form.get('quantity', 1))
    inventory_id = request.form.get('inventory_id')

    if not inventory_id:
        flash('Please select a size.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    db = get_db()
    inventory_item = db.execute("SELECT * FROM inventory WHERE id = ?", (inventory_id,)).fetchone()

    if not inventory_item:
        flash('Invalid product variant.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    # --- MODIFIED: Use a unique key: f"{product_id}-{inventory_id}" ---
    cart_key = f"{product_id}-{inventory_id}"

    current_quantity_in_cart = cart.get(cart_key, 0)
    
    # Stock Check
    if (quantity + current_quantity_in_cart) > inventory_item['stock_quantity']:
        flash(f"Sorry, we only have {inventory_item['stock_quantity']} items in stock for this size.", 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    cart[cart_key] = current_quantity_in_cart + quantity
    
    session['cart'] = cart
    flash(f'Added {quantity} item(s) to your cart!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
def view_cart():
    navigation_links = generate_content("navigation_links")
    cart_items = session.get('cart', {})
    
    if not cart_items:
        return render_template('cart.html', navigation_links=navigation_links, cart_products=[], total_price=0)
        
    db = get_db()
    cart_products_display = []
    # MODIFIED: Initialize new variables for cost breakdown
    total_sale_price = 0
    total_mrp = 0

    for cart_key, quantity in cart_items.items():
        product_id, inventory_id = cart_key.split('-')
        
        item_data = db.execute("""
            SELECT p.*, i.size, i.id as inventory_id FROM products p
            JOIN inventory i ON p.id = i.product_id
            WHERE p.id = ? AND i.id = ?
        """, (product_id, inventory_id)).fetchone()

        if item_data:
            processed_item = process_products([item_data])[0]
            subtotal = processed_item['sale_price'] * quantity
            total_sale_price += subtotal
            
            # NEW: Calculate the total MRP
            total_mrp += item_data['original_price'] * quantity
            
            processed_item['quantity'] = quantity
            processed_item['subtotal'] = subtotal
            processed_item['cart_key'] = cart_key
            
            available_inventory = db.execute(
                "SELECT id, size, stock_quantity FROM inventory WHERE product_id = ? ORDER BY size",
                (product_id,)
            ).fetchall()
            processed_item['available_inventory'] = available_inventory
            
            cart_products_display.append(processed_item)
    
    # --- NEW: Calculate final costs after the loop ---
    discount_on_mrp = total_mrp - total_sale_price
    
    # Conditional delivery charge
    delivery_charge = 0 if total_sale_price >= FREE_SHIPPING_THRESHOLD else DELIVERY_CHARGE
    
    final_total_price = total_sale_price + PLATFORM_FEE + delivery_charge

    return render_template('cart.html', 
                           navigation_links=navigation_links, 
                           cart_products=cart_products_display, 
                           # Pass all new cost variables to the template
                           total_mrp=total_mrp,
                           discount_on_mrp=discount_on_mrp,
                           platform_fee=PLATFORM_FEE,
                           delivery_charge=delivery_charge,
                           final_total_price=final_total_price)

@app.route('/update_cart/<cart_key>', methods=['POST'])
def update_cart(cart_key):
    cart = session.get('cart', {})
    if cart_key in cart:
        try:
            quantity = int(request.form.get('quantity', 1))
            new_inventory_id = int(request.form.get('inventory_id'))

            if quantity <= 0:
                # If quantity is 0 or less, remove the item
                del cart[cart_key]
                flash('Item removed from your cart.', 'success')
            else:
                db = get_db()
                # Stock Check for the new size
                new_inventory_item = db.execute("SELECT stock_quantity, product_id FROM inventory WHERE id = ?", (new_inventory_id,)).fetchone()
                if quantity > new_inventory_item['stock_quantity']:
                    flash(f"Sorry, only {new_inventory_item['stock_quantity']} items are in stock for the selected size.", 'error')
                    return redirect(url_for('view_cart'))

                # This is the "replace" logic. It works for both size and quantity changes.
                new_cart_key = f"{new_inventory_item['product_id']}-{new_inventory_id}"

                # Remove the old item
                cart.pop(cart_key, None)
                
                # Add the new/updated item. If the size was changed to one already in the cart,
                # this will simply update its quantity, which is the desired behavior.
                cart[new_cart_key] = quantity
                flash('Cart updated successfully.', 'success')

        except (ValueError, TypeError):
            flash('Invalid update request.', 'error')

    session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart/<cart_key>', methods=['POST'])
def remove_from_cart(cart_key):
    cart = session.get('cart', {})
    if cart_key in cart:
        del cart[cart_key]
    session['cart'] = cart
    flash('Item removed from your cart.', 'success')
    return redirect(url_for('view_cart'))
    
# STEP 1 of Checkout: The Order Summary Page
# --- NEW CONSOLIDATED CHECKOUT ROUTE ---
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    db = get_db()
    cart = session.get('cart', {})
    
    if not cart:
        flash("Your cart is empty.", "info")
        return redirect(url_for('view_cart'))

    # --- SHARED LOGIC: Calculate costs for both GET and POST ---
    total_sale_price = 0
    total_mrp = 0
    cart_products_display = []
    order_items_to_insert = []

    for cart_key, quantity in cart.items():
        product_id, inventory_id = cart_key.split('-')
        item_data = db.execute("""
            SELECT p.id, p.name, p.image_url, p.original_price, p.discount_percent, i.size, i.stock_quantity 
            FROM products p JOIN inventory i ON p.id = i.product_id WHERE i.id = ?
        """, (inventory_id,)).fetchone()

        if item_data:
            sale_price = item_data['original_price'] * (1 - item_data['discount_percent'] / 100.0)
            total_sale_price += sale_price * quantity
            total_mrp += item_data['original_price'] * quantity
            
            processed_item = process_products([item_data])[0]
            processed_item['quantity'] = quantity
            processed_item['subtotal'] = sale_price * quantity
            cart_products_display.append(processed_item)
            
            order_items_to_insert.append({
                "product_id": product_id, "inventory_id": inventory_id, "size": item_data['size'],
                "quantity": quantity, "price": sale_price, "stock": item_data['stock_quantity']
            })

    delivery_charge = 0 if total_sale_price >= FREE_SHIPPING_THRESHOLD else DELIVERY_CHARGE
    final_total_price = total_sale_price + PLATFORM_FEE + delivery_charge # Simplified total
    discount_on_mrp = total_mrp - total_sale_price

    # --- POST Request: Handle order submission ---
    if request.method == 'POST':
        # Update user details
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        phone = request.form.get('phone')
        db.execute("UPDATE users SET first_name = ?, last_name = ?, phone = ? WHERE id = ?",
                   (first_name, last_name, phone, current_user.id))

        # NEW: Capture the selected shipping address ID from the form
        selected_address_id = request.form.get('selected_address')
        if not selected_address_id:
            flash("Please select a shipping address.", "error")
            # We need to re-render the checkout page with all the necessary data
            # (This is a simplified redirect, a more complex implementation would re-render the template)
            return redirect(url_for('checkout'))

        payment_method = request.form.get('payment_method')

        # --- NEW: Determine the specific payment details to save ---
        payment_details = None # Default to None
        if payment_method == 'card':
            # In a real app, you'd get this from a payment gateway response.
            # For our simulation, we'll use the last 4 digits of the sample card.
            payment_details = "4242"
        elif payment_method == 'upi':
            # Get the selected UPI app (e.g., 'paytm', 'phonepe') and capitalize it
            upi_app = request.form.get('upi_app', 'UPI').capitalize()
            payment_details = upi_app

        # Stock check
        for item in order_items_to_insert:
            if item['quantity'] > item['stock']:
                flash(f"An item in your cart is out of stock. Please review your cart.", "error")
                return redirect(url_for('view_cart'))

        # Create the order (final_total_price is now the same for all methods)
        tracking_number = f"AWB{random.randint(100000000, 999999999)}IN"
        shipping_status = random.choice(['Processing', 'Shipped'])
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor = db.execute("""
            INSERT INTO orders (user_id, shipping_address_id, payment_method, payment_details, order_date, total_price, tracking_number, shipping_status) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (current_user.id, selected_address_id, payment_method, payment_details, current_time, final_total_price, tracking_number, shipping_status))
        new_order_id = cursor.lastrowid

        # Insert order items and decrement stock
        for item in order_items_to_insert:
            db.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", 
                       (new_order_id, item['product_id'], item['inventory_id'], item['size'], item['quantity'], item['price']))
            db.execute("UPDATE inventory SET stock_quantity = stock_quantity - ? WHERE id = ?",
                       (item['quantity'], item['inventory_id']))

        db.commit()
        session.pop('cart', None)
        flash(f'Your order has been placed successfully! Your Order ID is #{new_order_id}.', 'success')
        return redirect(url_for('checkout_success'))

    # --- GET Request: Display the checkout page ---
    user_data = db.execute("SELECT * FROM users WHERE id = ?", (current_user.id,)).fetchone()
    addresses = db.execute("SELECT * FROM addresses WHERE user_id = ? ORDER BY is_default DESC", (current_user.id,)).fetchall()
    navigation_links = generate_content("navigation_links")
    
    return render_template('checkout.html', 
                           navigation_links=navigation_links, 
                           user=user_data, 
                           addresses=addresses,
                           cart_products=cart_products_display, 
                           total_mrp=total_mrp, 
                           discount_on_mrp=discount_on_mrp,
                           platform_fee=PLATFORM_FEE, 
                           delivery_charge=delivery_charge,
                           final_total_price=final_total_price)

# STEP 3 of Checkout: The Success Page (No changes needed, but must exist)
@app.route('/checkout/success')
@login_required
def checkout_success():
    navigation_links = generate_content("navigation_links")
    return render_template('checkout_success.html', navigation_links=navigation_links)

@app.template_filter('k_format')
def k_format(num):
    """Formats a number into a 'k' format, e.g., 1700 -> 1.7k"""
    if num is None or num == 0:
        return '0'
    if num > 999:
        # Format to one decimal place, but remove .0 if it exists
        return f"{float(num/1000.0):.1f}".replace('.0', '') + "k"
    return str(num)

# --- NEW ROUTE TO FETCH MORE REVIEWS ---
@app.route('/get_reviews/<int:product_id>')
def get_reviews(product_id):
    page = request.args.get('page', 2, type=int)
    sort_by = request.args.get('sort', 'newest')
    
    offset = (page - 1) * REVIEWS_PER_PAGE
    
    order_clause = "ORDER BY r.review_date DESC" # Default
    if sort_by == 'oldest': order_clause = "ORDER BY r.review_date ASC"
    elif sort_by == 'highest': order_clause = "ORDER BY r.rating DESC, r.review_date DESC"
    elif sort_by == 'lowest': order_clause = "ORDER BY r.rating ASC, r.review_date DESC"

    db = get_db()
    reviews_data = db.execute(f"""
        SELECT r.rating, r.comment, u.username 
        FROM reviews r JOIN users u ON r.user_id = u.id 
        WHERE r.product_id = ? {order_clause} LIMIT ? OFFSET ?
    """, (product_id, REVIEWS_PER_PAGE, offset)).fetchall()
    
    # Convert the database rows to a list of dictionaries
    reviews_list = [dict(row) for row in reviews_data]
    
    return jsonify(reviews=reviews_list)

# NEW: Route to handle order cancellation
@app.route('/order/cancel/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    db = get_db()
    
    # Security check 1: Ensure the order belongs to the current user
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?",
        (order_id, current_user.id)
    ).fetchone()
    
    if order is None:
        flash("Order not found or you do not have permission to modify it.", "error")
        return redirect(url_for('my_orders'))

    # Security check 2: Ensure the order has not already been delivered or cancelled
    if order['shipping_status'] == 'Delivered' or order['status'] == 'Cancelled':
        flash("This order cannot be cancelled as it has already been delivered or cancelled.", "error")
        return redirect(url_for('order_details', order_id=order_id))

    # --- Step 1: Restore stock quantities for all items in the order ---
    order_items = db.execute("SELECT inventory_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    
    for item in order_items:
        db.execute("UPDATE inventory SET stock_quantity = stock_quantity + ? WHERE id = ?", 
                   (item['quantity'], item['inventory_id']))

    # --- Step 2: Update the order's status to 'Cancelled' ---
    db.execute("UPDATE orders SET status = 'Cancelled' WHERE id = ?", (order_id,))
    
    db.commit()
    
    flash(f"Order #{order_id} has been successfully cancelled.", "success")
    return redirect(url_for('my_orders'))


# ---- SocketIO Event Handlers for Chatbot with Memory ----

@socketio.on('connect')
def handle_connect():
    """Handles a new user connecting to the chatbot."""
    print('Client connected to chatbot')
    # Initialize an empty chat history in the user's session
    session['chat_history'] = []
    welcome_message = "Hello! I'm the Aura Apparel shopping assistant. How can I help you find the perfect sustainable clothing today?"
    # Add welcome message to history
    session['chat_history'].append({'role': 'assistant', 'content': welcome_message})
    response_payload = {
        "text": welcome_message,
        "products": [],
        "reviews": []
    }
    socketio.emit('bot_response', {'data': response_payload})

@socketio.on('user_message')
def handle_user_message(json):
    user_query = json['data']
    print(f'Received message: {user_query}')
    chat_history = session.get('chat_history', [])
    user_id = current_user.id if current_user.is_authenticated else None
    bot_reply = get_rag_response(user_query, chat_history, user_id)
    chat_history.append({'role': 'user', 'content': user_query})
    chat_history.append({'role': 'assistant', 'content': bot_reply['text']})
    session['chat_history'] = chat_history
    socketio.emit('bot_response', {'data': bot_reply})



if __name__ == '__main__':
    socketio.run(app, debug=True)