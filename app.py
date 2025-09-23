import os
import random
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, g, request, redirect, url_for, flash, session, jsonify
from flask_socketio import SocketIO
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras

# Import your custom modules
from chatbot_logic import get_rag_response
from ai_prompts import generate_content

# --- 1. APP SETUP & CONFIGURATION ---
app = Flask(__name__)

# IMPORTANT: REMOVE THIS AFTER YOU USE IT ONCE!
from setup_database import setup_database
@app.route('/super-secret-admin-setup-route-12345')
def run_database_setup():
    try:
        # We must explicitly tell psycopg2 to use SSL for this to work on Render
        os.environ['PGSSLMODE'] = 'require'
        setup_database()
        # Clean up the environment variable after use
        os.environ.pop('PGSSLMODE', None)
        return "SUCCESS: The database has been fully set up and seeded.", 200
    except Exception as e:
        os.environ.pop('PGSSLMODE', None)
        return f"ERROR: An error occurred during database setup: {e}", 500
# --- END OF TEMPORARY ROUTE ---


app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-super-secret-key-that-you-should-change')
# Use eventlet as the async mode for Gunicorn compatibility on Render

# --- THIS IS THE CRITICAL FIX ---
# Determine the async mode based on the environment.
# Gunicorn on Render will set the GUNICORN_CMD_ARGS environment variable.
IS_GUNICORN = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "")
if IS_GUNICORN:
    async_mode = 'eventlet'
else:
    async_mode = None  # Let Flask-SocketIO choose the best available

socketio = SocketIO(app, async_mode=async_mode)
# --- END OF FIX ---

# --- CONSTANTS ---
REVIEWS_PER_PAGE = 4
PLATFORM_FEE = 20
FREE_SHIPPING_THRESHOLD = 1499
DELIVERY_CHARGE = 50

# --- 2. LOGIN MANAGER SETUP ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = "info"

class User(UserMixin):
    def __init__(self, id, username, email, password_hash, first_name):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.first_name = first_name

@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    if user_data:
        return User(id=user_data['id'], username=user_data['username'], email=user_data['email'], password_hash=user_data['password_hash'], first_name=user_data['first_name'])
    return None

# --- 3. DATABASE CONNECTION ---
def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(os.getenv("DATABASE_URL"))
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- 4. HELPER FUNCTIONS & CONTEXT PROCESSORS ---
def process_products(products_data):
    processed = []
    for product in products_data:
        p = dict(product)
        if p.get('original_price') is not None and p.get('discount_percent') is not None:
            p['sale_price'] = float(p['original_price']) * (1 - p['discount_percent'] / 100.0)
        processed.append(p)
    return processed

@app.context_processor
def inject_global_variables():
    cart_items = session.get('cart', {})
    item_count = sum(cart_items.values())
    # This ensures a 'product' object is always available, even if None, to prevent template errors.
    return dict(cart_item_count=item_count, product=None)

@app.template_filter('k_format')
def k_format(num):
    if num is None or num == 0: return '0'
    if num > 999: return f"{float(num/1000.0):.1f}".replace('.0', '') + "k"
    return str(num)

# --- 5. MAIN ROUTES ---
@app.route('/')
def home():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # NULLS LAST is a PostgreSQL feature to handle products that may not have ratings yet
    cursor.execute("SELECT * FROM products ORDER BY rating DESC NULLS LAST, num_ratings DESC LIMIT 8")
    featured_products_data = cursor.fetchall()
    cursor.close()
    
    featured_products = process_products(featured_products_data)
    hero_content = generate_content("hero_section")
    trust_content = generate_content("trust_content")

    return render_template(
        'index.html',
        hero=hero_content,
        trust=trust_content,
        products=featured_products
    )

@app.route('/collection/desert-wanderer')
def desert_wanderer_collection():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    collection_ids = [18, 24, 25, 31, 37]
    placeholders = ','.join(['%s'] * len(collection_ids))
    
    cursor.execute(f"SELECT * FROM products WHERE id IN ({placeholders})", tuple(collection_ids))
    collection_products_data = cursor.fetchall()
    
    cursor.execute("SELECT DISTINCT brand FROM products ORDER BY brand")
    filter_brands_data = cursor.fetchall()
    cursor.close()

    products = process_products(collection_products_data)
    filter_brands = [row['brand'] for row in filter_brands_data]
    
    return render_template(
        'products.html',
        products=products,
        filter_brands=filter_brands,
        collection_title="The Desert Wanderer Collection",
        active_filters={},
        search_query=None,
        sort_by='name_asc'
    )

@app.route('/products')
def product_listing():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    category = request.args.get('category')
    brand = request.args.get('brand')
    search_query = request.args.get('q')
    price_range = request.args.get('price')
    rating = request.args.get('rating')
    sort_by = request.args.get('sort', 'relevance')

    # ILIKE is the case-insensitive version of LIKE in PostgreSQL
    base_query = "SELECT *, (original_price * (1 - discount_percent / 100.0)) as sale_price FROM products"
    params = []
    conditions = []

    if search_query:
        conditions.append("name ILIKE %s")
        params.append(f"%{search_query}%")

    if category:
        conditions.append("category = %s")
        params.append(category)
    if brand:
        conditions.append("brand = %s")
        params.append(brand)
    if rating:
        conditions.append("rating >= %s")
        params.append(float(rating))
    if price_range:
        low, high = price_range.split('-')
        conditions.append("(original_price * (1 - discount_percent / 100.0)) BETWEEN %s AND %s")
        params.extend([int(low), int(high)])

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)

    if sort_by == 'price_asc': base_query += " ORDER BY sale_price ASC"
    elif sort_by == 'price_desc': base_query += " ORDER BY sale_price DESC"
    elif sort_by == 'rating_desc': base_query += " ORDER BY rating DESC NULLS LAST"
    else: base_query += " ORDER BY name ASC"

    cursor.execute(base_query, tuple(params))
    all_products_data = cursor.fetchall()
    
    cursor.execute("SELECT DISTINCT brand FROM products ORDER BY brand")
    filter_brands_data = cursor.fetchall()
    cursor.close()

    filter_brands = [row['brand'] for row in filter_brands_data]

    return render_template(
        'products.html', 
        products=process_products(all_products_data),
        filter_brands=filter_brands,
        active_filters={'category': category, 'brand': brand, 'price': price_range, 'rating': rating},
        search_query=search_query, 
        sort_by=sort_by,
        collection_title=None
    )

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product_data = cursor.fetchone()
    if not product_data:
        cursor.close()
        return "Product not found", 404
    
    product = process_products([product_data])[0]
    
    cursor.execute("SELECT id, size, stock_quantity FROM inventory WHERE product_id = %s ORDER BY size", (product_id,))
    inventory = cursor.fetchall()

    sort_by = request.args.get('sort_reviews', 'newest')
    order_clause = "ORDER BY r.review_date DESC"
    if sort_by == 'oldest': order_clause = "ORDER BY r.review_date ASC"
    elif sort_by == 'highest': order_clause = "ORDER BY r.rating DESC, r.review_date DESC"
    elif sort_by == 'lowest': order_clause = "ORDER BY r.rating ASC, r.review_date DESC"

    cursor.execute(f"""
        SELECT r.rating, r.comment, u.username 
        FROM reviews r JOIN users u ON r.user_id = u.id 
        WHERE r.product_id = %s {order_clause} LIMIT %s
    """, (product_id, REVIEWS_PER_PAGE))
    reviews = cursor.fetchall()
    
    cursor.execute("SELECT * FROM products WHERE category = %s AND id != %s ORDER BY RANDOM() LIMIT 4", (product['category'], product_id))
    recommended_products_data = cursor.fetchall()
    
    is_in_wishlist = False
    if current_user.is_authenticated:
        cursor.execute("SELECT id FROM wishlist WHERE user_id = %s AND product_id = %s", (current_user.id, product_id))
        is_in_wishlist_data = cursor.fetchone()
        if is_in_wishlist_data: is_in_wishlist = True
    
    cursor.close()
    
    recommended_products = process_products(recommended_products_data)
    cart = session.get('cart', {})
    is_in_cart = any(key.startswith(f"{product_id}-") for key in cart.keys())
    
    return render_template(
        'product_detail.html', 
        product=product, 
        inventory=inventory,
        reviews=reviews,
        is_in_cart=is_in_cart,
        recommended_products=recommended_products,
        request=request,
        is_in_wishlist=is_in_wishlist,
        sort_by=sort_by
    )

@app.route('/quick_view/<int:product_id>')
def quick_view(product_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product_data = cursor.fetchone()
    cursor.close()
    
    if not product_data:
        return jsonify(error="Product not found"), 404
    
    product = process_products([product_data])[0]
    return render_template('quick_view_content.html', product=product)

@app.route('/live_search')
def live_search():
    query = request.args.get('q', '')
    if not query or len(query) < 2:
        return jsonify(products=[])

    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    search_term = f"%{query}%"
    cursor.execute("""
        SELECT * FROM products 
        WHERE name ILIKE %s OR brand ILIKE %s
        ORDER BY num_ratings DESC, rating DESC NULLS LAST
        LIMIT 5
    """, (search_term, search_term))
    products_data = cursor.fetchall()
    cursor.close()
    
    products = process_products(products_data)
    results = [
        {"id": p['id'], "name": p['name'], "brand": p['brand'], "image_url": p['image_url'], "sale_price": f"₹{p['sale_price']:.0f}"}
        for p in products
    ]
    return jsonify(products=results)

# --- 6. STATIC & INFO ROUTES ---
@app.route('/about')
def about():
    return render_template('about_us.html')

@app.route('/contact')
def contact():
    return render_template('static_page.html', title="Contact Us", content_key="contact")

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('static_page.html', title="Privacy Policy", content_key="privacy")

@app.route('/return-policy')
def return_policy():
    return render_template('static_page.html', title="Return Policy", content_key="return")

@app.route('/faq')
def faq():
    return render_template('static_page.html', title="Frequently Asked Questions", content_key="faq")

@app.route('/track-order', methods=['GET', 'POST'])
def track_order():
    order_details = None
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        if order_id:
            db = get_db()
            cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT id, order_date, shipping_status, tracking_number FROM orders WHERE id = %s", (order_id,))
            order_details = cursor.fetchone()
            cursor.close()
            if order_details is None:
                flash(f"Order ID #{order_id} not found. Please check the number and try again.", "error")
        else:
            flash("Please enter an Order ID.", "error")
    return render_template('track_order.html', order_details=order_details)

# --- 7. AUTHENTICATION ROUTES ---
def db_get_user(username):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user_data = cursor.fetchone()
    cursor.close()
    if user_data:
        return User(id=user_data['id'], username=user_data['username'], email=user_data['email'], password_hash=user_data['password_hash'], first_name=user_data['first_name'])
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        db = get_db()
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        phone = request.form['phone']
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user_by_username = cursor.fetchone()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user_by_email = cursor.fetchone()
        if user_by_username: flash('Username already exists.', 'error')
        elif user_by_email: flash('Email address already registered.', 'error')
        else:
            password_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (username, email, password_hash, first_name, last_name, phone) VALUES (%s, %s, %s, %s, %s, %s)",
                           (username, email, password_hash, first_name, last_name, phone))
            db.commit()
            flash('Registration successful! Please log in.', 'success')
            cursor.close()
            return redirect(url_for('login'))
        cursor.close()
    return render_template('register.html')

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
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- 8. USER ACCOUNT & ORDER ROUTES ---
@app.route('/account')
@login_required
def account():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM addresses WHERE user_id = %s AND is_default = TRUE", (current_user.id,))
    default_address = cursor.fetchone()
    cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY order_date DESC LIMIT 1", (current_user.id,))
    last_order = cursor.fetchone()
    cursor.close()
    return render_template('account_dashboard.html', default_address=default_address, last_order=last_order)

@app.route('/account/profile', methods=['GET', 'POST'])
@login_required
def account_profile():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        if 'update_details' in request.form:
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            phone = request.form.get('phone')
            cursor.execute("UPDATE users SET first_name = %s, last_name = %s, phone = %s WHERE id = %s", (first_name, last_name, phone, current_user.id))
            db.commit()
            flash('Your personal details have been updated.', 'success')
        elif 'change_password' in request.form:
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            cursor.execute("SELECT password_hash FROM users WHERE id = %s", (current_user.id,))
            user = cursor.fetchone()
            if not check_password_hash(user['password_hash'], current_password):
                flash('Your current password does not match.', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match.', 'error')
            else:
                new_hash = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, current_user.id))
                db.commit()
                flash('Your password has been changed successfully.', 'success')
        cursor.close()
        return redirect(url_for('account_profile'))
    
    cursor.execute("SELECT * FROM users WHERE id = %s", (current_user.id,))
    user_data = cursor.fetchone()
    cursor.close()
    return render_template('account_profile.html', user=user_data)

@app.route('/account/addresses', methods=['GET', 'POST'])
@login_required
def account_addresses():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            cursor.execute("INSERT INTO addresses (user_id, address, city, state, zip_code) VALUES (%s, %s, %s, %s, %s)",
                           (current_user.id, request.form.get('address'), request.form.get('city'), request.form.get('state'), request.form.get('zip_code')))
            flash('New address added.', 'success')
        elif action == 'delete':
            address_id = request.form.get('address_id')
            cursor.execute("DELETE FROM addresses WHERE id = %s AND user_id = %s", (address_id, current_user.id))
            flash('Address removed.', 'success')
        elif action == 'set_default':
            address_id = request.form.get('address_id')
            cursor.execute("UPDATE addresses SET is_default = FALSE WHERE user_id = %s", (current_user.id,))
            cursor.execute("UPDATE addresses SET is_default = TRUE WHERE id = %s AND user_id = %s", (address_id, current_user.id))
            flash('Default address updated.', 'success')
        db.commit()
        cursor.close()
        return redirect(url_for('account_addresses'))

    cursor.execute("SELECT * FROM addresses WHERE user_id = %s ORDER BY is_default DESC", (current_user.id,))
    addresses = cursor.fetchall()
    cursor.close()
    return render_template('account_addresses.html', addresses=addresses)

@app.route('/my-orders')
@login_required
def my_orders():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY order_date DESC", (current_user.id,))
    user_orders_data = cursor.fetchall()
    
    orders = []
    for order_data in user_orders_data:
        cursor.execute("""
            SELECT p.name, oi.quantity, oi.price, oi.id as order_item_id, oi.has_reviewed
            FROM order_items oi JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = %s
        """, (order_data['id'],))
        items_data = cursor.fetchall()
        orders.append({
            'id': order_data['id'], 'date': order_data['order_date'], 'total': order_data['total_price'],
            'status': order_data['status'], 'shipping_status': order_data['shipping_status'],
            'order_products': [dict(row) for row in items_data]
        })
    cursor.close()
    return render_template('my_orders.html', orders=orders)

@app.route('/order/<int:order_id>')
@login_required
def order_details(order_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cursor.fetchone()
    if not order:
        cursor.close()
        flash("Order not found.", "error")
        return redirect(url_for('my_orders'))
    cursor.execute("""
        SELECT p.id as product_id, p.name, p.image_url, oi.quantity, oi.price as price_paid, oi.size
        FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = %s
    """, (order_id,))
    order_items_data = cursor.fetchall()
    cursor.execute("SELECT * FROM addresses WHERE id = %s", (order['shipping_address_id'],))
    shipping_address = cursor.fetchone()
    cursor.close()
    order_items = [dict(row) for row in order_items_data]
    subtotal = sum(float(item['price_paid']) * item['quantity'] for item in order_items)
    delivery_charge = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else DELIVERY_CHARGE
    return render_template('order_details.html', order=order, order_items=order_items, shipping_address=shipping_address, subtotal=subtotal, delivery_charge=delivery_charge, platform_fee=PLATFORM_FEE, order_date=order['order_date'])

# --- 9. CART & CHECKOUT ROUTES ---
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    cart = session.get('cart', {})
    quantity = int(request.form.get('quantity', 1))
    inventory_id = request.form.get('inventory_id')
    if not inventory_id:
        flash('Please select a size.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM inventory WHERE id = %s", (inventory_id,))
    inventory_item = cursor.fetchone()
    cursor.close()
    if not inventory_item:
        flash('Invalid product variant.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    cart_key = f"{product_id}-{inventory_id}"
    current_quantity = cart.get(cart_key, 0)
    if (quantity + current_quantity) > inventory_item['stock_quantity']:
        flash(f"Sorry, only {inventory_item['stock_quantity']} items are in stock for this size.", 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    cart[cart_key] = current_quantity + quantity
    session['cart'] = cart
    flash(f'Added {quantity} item(s) to your cart!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
def view_cart():
    cart_items = session.get('cart', {})
    if not cart_items:
        return render_template('cart.html', cart_products=[], final_total_price=0, total_mrp=0, discount_on_mrp=0, platform_fee=0, delivery_charge=0)
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cart_products_display = []
    total_sale_price = 0
    total_mrp = 0
    for cart_key, quantity in cart_items.items():
        product_id, inventory_id = cart_key.split('-')
        cursor.execute("SELECT p.*, i.size, i.id as inventory_id FROM products p JOIN inventory i ON p.id = i.product_id WHERE p.id = %s AND i.id = %s", (product_id, inventory_id))
        item_data = cursor.fetchone()
        if item_data:
            processed_item = process_products([item_data])[0]
            total_sale_price += processed_item['sale_price'] * quantity
            total_mrp += float(item_data['original_price']) * quantity
            processed_item.update({'quantity': quantity, 'subtotal': processed_item['sale_price'] * quantity, 'cart_key': cart_key})
            cursor.execute("SELECT id, size, stock_quantity FROM inventory WHERE product_id = %s ORDER BY size", (product_id,))
            processed_item['available_inventory'] = cursor.fetchall()
            cart_products_display.append(processed_item)
    cursor.close()
    discount_on_mrp = total_mrp - total_sale_price
    delivery_charge = 0 if total_sale_price >= FREE_SHIPPING_THRESHOLD else DELIVERY_CHARGE
    final_total_price = total_sale_price + PLATFORM_FEE + delivery_charge
    return render_template('cart.html', cart_products=cart_products_display, total_mrp=total_mrp, discount_on_mrp=discount_on_mrp, platform_fee=PLATFORM_FEE, delivery_charge=delivery_charge, final_total_price=final_total_price)

@app.route('/update_cart/<cart_key>', methods=['POST'])
def update_cart(cart_key):
    cart = session.get('cart', {})
    if cart_key in cart:
        try:
            quantity = int(request.form.get('quantity', 1))
            new_inventory_id = int(request.form.get('inventory_id'))

            # If quantity is set to 0 or less, it should be treated as a removal.
            if quantity <= 0:
                cart.pop(cart_key, None)
                flash('Item removed from cart.', 'success')
            else:
                db = get_db()
                cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cursor.execute("SELECT stock_quantity, product_id FROM inventory WHERE id = %s", (new_inventory_id,))
                new_inventory_item = cursor.fetchone()
                cursor.close()

                if quantity > new_inventory_item['stock_quantity']:
                    flash(f"Sorry, only {new_inventory_item['stock_quantity']} items are in stock.", 'error')
                else:
                    new_cart_key = f"{new_inventory_item['product_id']}-{new_inventory_id}"
                    # Remove the old item regardless of whether the size changed
                    cart.pop(cart_key, None)
                    # Add the new or updated item
                    cart[new_cart_key] = quantity
                    flash('Cart updated.', 'success')
        except (ValueError, TypeError):
            flash('Invalid update.', 'error')
    
    session['cart'] = cart
    session.modified = True # Ensure the session is saved
    return redirect(url_for('view_cart'))

@app.route('/remove_from_cart/<cart_key>', methods=['POST'])
def remove_from_cart(cart_key):
    cart = session.get('cart', {})
    
    # Use .pop() which safely removes a key and returns None if it's not found
    if cart.pop(cart_key, None):
        flash('Item removed from your cart.', 'success')
    
    session['cart'] = cart
    session.modified = True # Ensure the session is saved
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty.", "info")
        return redirect(url_for('view_cart'))
    
    total_sale_price = 0
    total_mrp = 0
    order_items_to_insert = []
    cart_products_display = []
    
    for cart_key, quantity in cart.items():
        product_id, inventory_id = cart_key.split('-')
        cursor.execute("SELECT p.*, i.size, i.stock_quantity FROM products p JOIN inventory i ON p.id = i.product_id WHERE i.id = %s", (inventory_id,))
        item_data = cursor.fetchone()
        if item_data:
            sale_price = float(item_data['original_price']) * (1 - item_data['discount_percent'] / 100.0)
            total_sale_price += sale_price * quantity
            total_mrp += float(item_data['original_price']) * quantity
            cart_products_display.append({'name': item_data['name'], 'quantity': quantity, 'subtotal': sale_price * quantity, 'image_url': item_data['image_url'], 'size': item_data['size']})
            order_items_to_insert.append({"product_id": product_id, "inventory_id": inventory_id, "size": item_data['size'], "quantity": quantity, "price": sale_price, "stock": item_data['stock_quantity']})

    delivery_charge = 0 if total_sale_price >= FREE_SHIPPING_THRESHOLD else DELIVERY_CHARGE
    final_total_price = total_sale_price + PLATFORM_FEE + delivery_charge
    discount_on_mrp = total_mrp - total_sale_price

    if request.method == 'POST':
        selected_address_id = request.form.get('selected_address')
        if not selected_address_id:
            flash("Please select a shipping address.", "error")
            return redirect(url_for('checkout'))
        
        for item in order_items_to_insert:
            if item['quantity'] > item['stock']:
                flash(f"An item in your cart is out of stock. Please review your cart.", "error")
                return redirect(url_for('view_cart'))
        
        payment_method = request.form.get('payment_method')
        payment_details = None
        if payment_method == 'card': payment_details = "4242"
        elif payment_method == 'upi': payment_details = request.form.get('upi_app', 'UPI').capitalize()
        
        current_time = datetime.now()
        tracking_number = f"AWB{random.randint(100000000, 999999999)}IN"
        shipping_status = random.choice(['Processing', 'Shipped'])
        
        cursor.execute("INSERT INTO orders (user_id, shipping_address_id, payment_method, payment_details, order_date, total_price, tracking_number, shipping_status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                       (current_user.id, selected_address_id, payment_method, payment_details, current_time, final_total_price, tracking_number, shipping_status))
        new_order_id = cursor.fetchone()['id']
        
        for item in order_items_to_insert:
            cursor.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (%s, %s, %s, %s, %s, %s)",
                           (new_order_id, item['product_id'], item['inventory_id'], item['size'], item['quantity'], item['price']))
            cursor.execute("UPDATE inventory SET stock_quantity = stock_quantity - %s WHERE id = %s",
                           (item['quantity'], item['inventory_id']))
        db.commit()
        cursor.close()
        session.pop('cart', None)
        flash(f'Your order has been placed successfully! Your Order ID is #{new_order_id}.', 'success')
        return redirect(url_for('checkout_success'))

    cursor.execute("SELECT * FROM users WHERE id = %s", (current_user.id,))
    user_data = cursor.fetchone()
    cursor.execute("SELECT * FROM addresses WHERE user_id = %s ORDER BY is_default DESC", (current_user.id,))
    addresses = cursor.fetchall()
    cursor.close()
    
    return render_template('checkout.html', user=user_data, addresses=addresses, cart_products=cart_products_display, total_mrp=total_mrp, discount_on_mrp=discount_on_mrp, platform_fee=PLATFORM_FEE, delivery_charge=delivery_charge, final_total_price=final_total_price)

@app.route('/checkout/success')
@login_required
def checkout_success():
    return render_template('checkout_success.html')

# --- 10. WISHLIST, REVIEWS, & ORDER MANAGEMENT ---
@app.route('/wishlist')
@login_required
def wishlist():
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT p.* FROM products p JOIN wishlist w ON p.id = w.product_id WHERE w.user_id = %s", (current_user.id,))
    wishlist_items_data = cursor.fetchall()
    cursor.close()
    wishlist_items = process_products(wishlist_items_data)
    return render_template('wishlist.html', products=wishlist_items)

@app.route('/wishlist/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_wishlist(product_id):
    db = get_db()
    cursor = db.cursor()
    try:
        current_time = datetime.now()
        cursor.execute("INSERT INTO wishlist (user_id, product_id, added_date) VALUES (%s, %s, %s)", (current_user.id, product_id, current_time))
        db.commit()
        flash('Item added to your wishlist!', 'success')
    except psycopg2.IntegrityError:
        db.rollback()
        flash('This item is already in your wishlist.', 'info')
    finally:
        cursor.close()
    return redirect(request.referrer)

@app.route('/wishlist/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_wishlist(product_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM wishlist WHERE user_id = %s AND product_id = %s", (current_user.id, product_id))
    db.commit()
    cursor.close()
    flash('Item removed from your wishlist.', 'success')
    return redirect(request.referrer)

@app.route('/leave_review/<int:order_item_id>')
@login_required
def leave_review(order_item_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""
        SELECT oi.id, oi.product_id, p.name FROM order_items oi
        JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id
        WHERE oi.id = %s AND o.user_id = %s AND oi.has_reviewed = FALSE
    """, (order_item_id, current_user.id))
    item = cursor.fetchone()
    cursor.close()
    if item is None:
        flash("You are not eligible to review this item, or it has already been reviewed.", "error")
        return redirect(url_for('my_orders'))
    return render_template('review.html', order_item_id=order_item_id, product=item)

@app.route('/submit_review/<int:order_item_id>', methods=['POST'])
@login_required
def submit_review(order_item_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT oi.id, oi.product_id FROM order_items oi JOIN orders o ON oi.order_id = o.id WHERE oi.id = %s AND o.user_id = %s AND oi.has_reviewed = FALSE", (order_item_id, current_user.id))
    item = cursor.fetchone()
    if item is None:
        cursor.close()
        flash("Review submission failed. Item may already be reviewed.", "error")
        return redirect(url_for('my_orders'))
    rating = request.form['rating']
    comment = request.form['comment']
    product_id = item['product_id']
    current_time = datetime.now()
    cursor.execute("INSERT INTO reviews (product_id, user_id, rating, comment, review_date) VALUES (%s, %s, %s, %s, %s)",
                   (product_id, current_user.id, rating, comment, current_time))
    cursor.execute("UPDATE order_items SET has_reviewed = TRUE WHERE id = %s", (order_item_id,))
    cursor.execute("SELECT AVG(rating) as avg, COUNT(id) as count FROM reviews WHERE product_id = %s", (product_id,))
    stats = cursor.fetchone()
    if stats:
        cursor.execute("UPDATE products SET rating = %s, num_ratings = %s WHERE id = %s", (stats['avg'], stats['count'], product_id))
    db.commit()
    cursor.close()
    flash("Thank you for your review!", "success")
    return redirect(url_for('my_orders'))

@app.route('/request_return/<int:order_id>', methods=['POST'])
@login_required
def request_return(order_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cursor.fetchone()
    if order is None:
        cursor.close()
        flash("Order not found or access denied.", "error")
        return redirect(url_for('my_orders'))
    cursor.execute("UPDATE orders SET status = 'Return Requested' WHERE id = %s", (order_id,))
    db.commit()
    cursor.close()
    flash(f"Return requested for Order #{order_id}. You will be contacted shortly.", "success")
    return redirect(url_for('my_orders'))

@app.route('/order/cancel/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM orders WHERE id = %s AND user_id = %s", (order_id, current_user.id))
    order = cursor.fetchone()
    if order is None:
        cursor.close(); flash("Order not found.", "error"); return redirect(url_for('my_orders'))
    if order['shipping_status'] == 'Delivered' or order['status'] == 'Cancelled':
        cursor.close(); flash("This order cannot be cancelled.", "error"); return redirect(url_for('order_details', order_id=order_id))
    cursor.execute("SELECT inventory_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
    order_items = cursor.fetchall()
    for item in order_items:
        cursor.execute("UPDATE inventory SET stock_quantity = stock_quantity + %s WHERE id = %s", (item['quantity'], item['inventory_id']))
    cursor.execute("UPDATE orders SET status = 'Cancelled' WHERE id = %s", (order_id,))
    db.commit()
    cursor.close()
    flash(f"Order #{order_id} has been cancelled.", "success")
    return redirect(url_for('my_orders'))

@app.route('/get_reviews/<int:product_id>')
def get_reviews(product_id):
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'newest')
    offset = (page - 1) * REVIEWS_PER_PAGE
    order_clause = "ORDER BY r.review_date DESC"
    if sort_by == 'oldest': order_clause = "ORDER BY r.review_date ASC"
    elif sort_by == 'highest': order_clause = "ORDER BY r.rating DESC, r.review_date DESC"
    elif sort_by == 'lowest': order_clause = "ORDER BY r.rating ASC, r.review_date DESC"
    db = get_db()
    cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(f"""
        SELECT r.rating, r.comment, u.username FROM reviews r JOIN users u ON r.user_id = u.id 
        WHERE r.product_id = %s {order_clause} LIMIT %s OFFSET %s
    """, (product_id, REVIEWS_PER_PAGE, offset))
    reviews_data = cursor.fetchall()
    cursor.close()
    return jsonify(reviews=[dict(row) for row in reviews_data])

# --- 11. SOCKETIO CHATBOT ---
@socketio.on('connect')
def handle_connect():
    print('Client connected to chatbot')
    session['chat_history'] = []
    welcome_message = "Hello! I'm Aura Assistant. How can I help?"
    session['chat_history'].append({'role': 'assistant', 'content': welcome_message})
    socketio.emit('bot_response', {'data': {"text": welcome_message, "products": []}})

@socketio.on('user_message')
def handle_user_message(json):
    try:  # --- START OF NEW ERROR HANDLING
        user_query = json['data']
        chat_history = session.get('chat_history', [])
        user_id = current_user.id if current_user.is_authenticated else None
        
        bot_reply = get_rag_response(user_query, chat_history, user_id)
        
        chat_history.append({'role': 'user', 'content': user_query})
        chat_history.append({'role': 'assistant', 'content': bot_reply['text']})
        session['chat_history'] = chat_history
        
        socketio.emit('bot_response', {'data': bot_reply})
    except Exception as e:
        # If ANY error occurs, log it to the server and send a safe message to the user
        print(f"--- UNHANDLED ERROR IN CHATBOT: {e} ---")
        error_reply = {
            "text": "I'm sorry, I seem to have encountered an unexpected error. Please try a different question.",
            "products": [],
            "orders": []
        }
        socketio.emit('bot_response', {'data': error_reply})
    # --- END OF NEW ERROR HANDLING

if __name__ == '__main__':
    socketio.run(app)