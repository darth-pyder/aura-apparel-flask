import sqlite3
import random
import os
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# --- Configuration ---
INR_EXCHANGE_RATE = 83.50

# --- Helper Function 1 ---
def get_brand_for_product(name):
    name = name.lower()
    if any(keyword in name for keyword in ['athletic', 'compression', 'running', 'track', 'workout', 'leggings', 'jogger', 'sweatpant', 'sleeveless hoodie', 'moisture-wicking', 'tank top']):
        return "Aura Active"
    if any(keyword in name for keyword in ['jeans', 'denim']):
        return "Aura Denim"
    if any(keyword in name for keyword in ['formal', 'sweater', 'flannel', 'linen', 'tropical', 'cargo', 'trousers', 'bomber', 'leather', 'trench', 'puffer', 'blazer']):
        return "Aura Luxe"
    return "Aura Basics"

# --- Helper Function 2 (The new test user function) ---
def create_dedicated_test_user(cursor):
    """Creates a special test user with a rich order history."""
    print("\n--- Creating Dedicated Test User ---")
    
    # User Details
    username = "dias_antony"
    email = "dias@myre.com"
    password = "dias123"
    first_name = "Dias"
    last_name = "Antony"
    phone = "987-654-3210"

    # Insert user and get their new ID
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, first_name, last_name, phone) VALUES (?, ?, ?, ?, ?, ?)",
            (username, email, generate_password_hash(password), first_name, last_name, phone)
        )
        test_user_id = cursor.lastrowid
        print(f"Created user '{username}' with ID: {test_user_id}")

        # User Addresses
        addresses = [
            {'address': '101 Tech Park Road', 'city': 'Hyderabad', 'state': 'Telangana', 'zip_code': '500081', 'is_default': 1},
            {'address': '25B Creative Circle', 'city': 'Bangalore', 'state': 'Karnataka', 'zip_code': '560001', 'is_default': 0}
        ]
        address_ids = []
        for addr in addresses:
            cursor.execute(
                "INSERT INTO addresses (user_id, address, city, state, zip_code, is_default) VALUES (?, ?, ?, ?, ?, ?)",
                (test_user_id, addr['address'], addr['city'], addr['state'], addr['zip_code'], addr['is_default'])
            )
            address_ids.append(cursor.lastrowid)
        print(f"Added {len(addresses)} addresses for {username}.")

        # User Order History
        # Order 1: Delivered (Eligible for Return)
        order1_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, shipping_address_id, payment_method, payment_details, order_date, total_price, status, tracking_number, shipping_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (test_user_id, address_ids[0], 'card', '4242', order1_date, 1789.0, 'Completed', f"AWB{random.randint(100000000, 999999999)}IN", 'Delivered'))
        order1_id = cursor.lastrowid
        cursor.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", (order1_id, 4, 18, 'L', 1, 899))
        cursor.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", (order1_id, 24, 118, '34', 1, 890))

        # Order 2: In Transit (Eligible for Cancellation)
        order2_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, shipping_address_id, payment_method, payment_details, order_date, total_price, status, tracking_number, shipping_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (test_user_id, address_ids[1], 'upi', 'Paytm', order2_date, 2518.0, 'Completed', f"AWB{random.randint(100000000, 999999999)}IN", 'In Transit'))
        order2_id = cursor.lastrowid
        cursor.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", (order2_id, 36, 178, 'L', 1, 2448))

        # Order 3: Return Requested
        order3_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, shipping_address_id, payment_method, payment_details, order_date, total_price, status, tracking_number, shipping_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (test_user_id, address_ids[0], 'cod', None, order3_date, 1969.0, 'Return Requested', f"AWB{random.randint(100000000, 999999999)}IN", 'Delivered'))
        order3_id = cursor.lastrowid
        cursor.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", (order3_id, 15, 73, 'M', 1, 1899))

        # Order 4: Cancelled
        order4_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO orders (user_id, shipping_address_id, payment_method, payment_details, order_date, total_price, status, tracking_number, shipping_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (test_user_id, address_ids[0], 'card', '4242', order4_date, 1069.0, 'Cancelled', f"AWB{random.randint(100000000, 999999999)}IN", 'Processing'))
        order4_id = cursor.lastrowid
        cursor.execute("INSERT INTO order_items (order_id, product_id, inventory_id, size, quantity, price) VALUES (?, ?, ?, ?, ?, ?)", (order4_id, 6, 28, 'L', 1, 999))

        print("Finished creating dedicated test user and their order history.")
    else:
        print(f"User '{username}' already exists. Skipping creation.")

# --- Main Database Setup Function ---
def setup_database():
    INSTANCE_FOLDER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
    DATABASE_PATH = os.path.join(INSTANCE_FOLDER_PATH, 'products.db')

    # Create the instance folder if it doesn't exist
    os.makedirs(INSTANCE_FOLDER_PATH, exist_ok=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    conn = sqlite3.connect(DATABASE_PATH)

    # Drop all tables
    print("Dropping old tables if they exist...")
    # ... (all DROP TABLE statements) ...
    cursor.execute("DROP TABLE IF EXISTS reviews")
    cursor.execute("DROP TABLE IF EXISTS order_items")
    cursor.execute("DROP TABLE IF EXISTS orders")
    cursor.execute("DROP TABLE IF EXISTS inventory")
    cursor.execute("DROP TABLE IF EXISTS addresses")
    cursor.execute("DROP TABLE IF EXISTS products")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS wishlist")
    print("Old tables dropped.")

    # Recreate all tables
    print("Creating new tables with the final schema...")
    # ... (all CREATE TABLE statements) ...
    cursor.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, long_description TEXT, original_price REAL NOT NULL, discount_percent INTEGER NOT NULL DEFAULT 0, image_url TEXT, category TEXT, brand TEXT, color TEXT, rating REAL, num_ratings INTEGER NOT NULL DEFAULT 0);")
    cursor.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, size TEXT NOT NULL, stock_quantity INTEGER NOT NULL, FOREIGN KEY (product_id) REFERENCES products(id), UNIQUE(product_id, size));")
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL, phone TEXT NOT NULL);")
    cursor.execute("CREATE TABLE addresses (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, address TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL, zip_code TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0, FOREIGN KEY (user_id) REFERENCES users(id));")
    cursor.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, shipping_address_id INTEGER NOT NULL, payment_method TEXT NOT NULL, payment_details TEXT, order_date TEXT NOT NULL, total_price REAL NOT NULL, status TEXT DEFAULT 'Completed', tracking_number TEXT, shipping_status TEXT, FOREIGN KEY (user_id) REFERENCES users (id), FOREIGN KEY (shipping_address_id) REFERENCES addresses (id));")
    cursor.execute("CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, product_id INTEGER NOT NULL, inventory_id INTEGER NOT NULL, size TEXT NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL, has_reviewed INTEGER NOT NULL DEFAULT 0, FOREIGN KEY (order_id) REFERENCES orders (id), FOREIGN KEY (product_id) REFERENCES products (id), FOREIGN KEY (inventory_id) REFERENCES inventory (id));")
    cursor.execute("CREATE TABLE reviews (id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, user_id INTEGER NOT NULL, rating INTEGER NOT NULL, comment TEXT NOT NULL, review_date TEXT NOT NULL, FOREIGN KEY (product_id) REFERENCES products (id), FOREIGN KEY (user_id) REFERENCES users (id));")
    cursor.execute("CREATE TABLE wishlist (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, product_id INTEGER NOT NULL, added_date TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users (id), FOREIGN KEY (product_id) REFERENCES products (id), UNIQUE(user_id, product_id));")
    print("All tables recreated successfully.")

    # Populate products
    products = [
        {"id": 1, "name": "Men’s black Graphic Print Slim Fit Crew-Neck T-Shirt", "category": "Tops", "color": "Black"}, {"id": 2, "name": "Men’s black graphic t-shirt, casual fit", "category": "Tops", "color": "Black"}, {"id": 3, "name": "Men’s white graphic t-shirt, relaxed fit", "category": "Tops", "color": "White"}, {"id": 4, "name": "Men’s grey plain t-shirt, slim fit", "category": "Tops", "color": "Grey"}, {"id": 5, "name": "Men’s classic fit polo shirt, navy blue", "category": "Tops", "color": "Navy Blue"}, {"id": 6, "name": "Men’s slim fit polo shirt, white", "category": "Tops", "color": "White"}, {"id": 7, "name": "Men’s blue casual button-down shirt, long sleeve", "category": "Tops", "color": "Blue"}, {"id": 8, "name": "Men’s white formal button-down shirt, long sleeve", "category": "Tops", "color": "White"}, {"id": 9, "name": "Men’s long sleeve henley shirt, charcoal grey", "category": "Tops", "color": "Charcoal Grey"}, {"id": 10, "name": "Men’s short sleeve henley shirt, olive green", "category": "Tops", "color": "Olive Green"}, {"id": 11, "name": "Men’s black tank top, athletic fit", "category": "Tops", "color": "Black"}, {"id": 12, "name": "Men’s white tank top, athletic fit", "category": "Tops", "color": "White"}, {"id": 13, "name": "Men’s grey crew neck sweater, knit", "category": "Tops", "color": "Grey"}, {"id": 14, "name": "Men’s navy v-neck sweater, knit", "category": "Tops", "color": "Navy"}, {"id": 15, "name": "Men’s logo print sweatshirt, black", "category": "Tops", "color": "Black"}, {"id": 16, "name": "Men’s plain sweatshirt, heather grey", "category": "Tops", "color": "Heather Grey"}, {"id": 17, "name": "Men’s red plaid flannel shirt, long sleeve", "category": "Tops", "color": "Red"}, {"id": 18, "name": "Men’s beige linen shirt, long sleeve", "category": "Tops", "color": "Beige"}, {"id": 19, "name": "Men’s short sleeve tropical print shirt, colorful", "category": "Tops", "color": "Multi-color"}, {"id": 20, "name": "Men’s striped rugby shirt, navy and white, long sleeve", "category": "Tops", "color": "Navy/White"}, {"id": 21, "name": "Men’s skinny jeans, dark wash", "category": "Bottoms", "color": "Dark Wash"}, {"id": 22, "name": "Men’s straight jeans, light wash", "category": "Bottoms", "color": "Light Wash"}, {"id": 23, "name": "Men’s slim fit jeans, black", "category": "Bottoms", "color": "Black"}, {"id": 24, "name": "Men’s khaki chinos, classic fit", "category": "Bottoms", "color": "Khaki"}, {"id": 25, "name": "Men’s olive chinos, slim fit", "category": "Bottoms", "color": "Olive"}, {"id": 26, "name": "Men’s grey joggers, drawstring waist", "category": "Bottoms", "color": "Grey"}, {"id": 27, "name": "Men’s black joggers, tapered fit", "category": "Bottoms", "color": "Black"}, {"id": 28, "name": "Men’s green cargo pants, multiple pockets", "category": "Bottoms", "color": "Green"}, {"id": 29, "name": "Men’s navy dress trousers, tailored fit", "category": "Bottoms", "color": "Navy"}, {"id": 30, "name": "Men’s blue denim shorts, casual fit", "category": "Bottoms", "color": "Blue"}, {"id": 31, "name": "Men’s beige chino shorts, classic fit", "category": "Bottoms", "color": "Beige"}, {"id": 32, "name": "Men’s black athletic shorts, moisture-wicking", "category": "Bottoms", "color": "Black"}, {"id": 33, "name": "Men’s navy athletic shorts, lightweight", "category": "Bottoms", "color": "Navy"}, {"id": 34, "name": "Men’s charcoal sweatpants, relaxed fit", "category": "Bottoms", "color": "Charcoal"}, {"id": 35, "name": "Men’s blue denim jacket, classic fit", "category": "Outerwear", "color": "Blue"}, {"id": 36, "name": "Men’s black bomber jacket, zip-up", "category": "Outerwear", "color": "Black"}, {"id": 37, "name": "Men’s brown leather jacket, biker style", "category": "Outerwear", "color": "Brown"}, {"id": 38, "name": "Men’s camel trench coat, belted", "category": "Outerwear", "color": "Camel"}, {"id": 39, "name": "Men’s navy puffer jacket, quilted", "category": "Outerwear", "color": "Navy"}, {"id": 40, "name": "Men’s grey zip-up hoodie, casual fit", "category": "Outerwear", "color": "Grey"}, {"id": 41, "name": "Men’s black pullover hoodie, classic fit", "category": "Outerwear", "color": "Black"}, {"id": 42, "name": "Men’s charcoal blazer, tailored fit", "category": "Outerwear", "color": "Charcoal"}, {"id": 43, "name": "Men’s black compression shirt, short sleeve", "category": "Activewear", "color": "Black"}, {"id": 44, "name": "Men’s white compression shirt, long sleeve", "category": "Activewear", "color": "White"}, {"id": 45, "name": "Men’s grey athletic tank top, moisture-wicking", "category": "Activewear", "color": "Grey"}, {"id": 46, "name": "Men’s blue running shorts, lightweight", "category": "Activewear", "color": "Blue"}, {"id": 47, "name": "Men’s black track jacket, zip-up", "category": "Activewear", "color": "Black"}, {"id": 48, "name": "Men’s navy workout t-shirt, moisture-wicking", "category": "Activewear", "color": "Navy"}, {"id": 49, "name": "Men’s black athletic leggings, fitted", "category": "Activewear", "color": "Black"}, {"id": 50, "name": "Men’s grey sleeveless hoodie, athletic fit", "category": "Activewear", "color": "Grey"},
    ]
    for product in products:
        # ... (product insertion logic) ...
        name = product['name']
        brand = get_brand_for_product(name)
        short_desc = name.replace("Men’s", "").split(",")[0].strip().capitalize()
        long_desc = f"Discover the perfect blend of style and comfort with our {name}. Crafted from premium materials, this piece is designed for a modern fit and long-lasting wear."
        price_map_usd = {"Tops": (15, 60), "Bottoms": (40, 90), "Outerwear": (70, 250), "Activewear": (25, 70)}
        price_usd = round(random.uniform(*price_map_usd.get(product['category'], (20, 60))), 2)
        original_price = round(price_usd * INR_EXCHANGE_RATE, -1) - 1
        discount = random.choice([0, 0, 10, 15, 20, 25, 30, 40, 50])
        image_filename = f"{product['id']}.png"
        
        cursor.execute("INSERT INTO products (id, name, description, long_description, original_price, discount_percent, image_url, category, brand, color, rating, num_ratings) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (product['id'], name, short_desc, long_desc, original_price, discount, image_filename, product['category'], brand, product['color'], 0, 0))
        size_list = ["S", "M", "L", "XL", "XXL"] if product['category'] in ["Tops", "Outerwear", "Activewear"] else ["30", "32", "34", "36", "38"]
        for size in size_list:
            stock = random.choice([0, random.randint(5, 50)])
            cursor.execute("INSERT INTO inventory (product_id, size, stock_quantity) VALUES (?, ?, ?)", (product['id'], size, stock))
    print(f"{len(products)} products and their inventory inserted.")

    # Populate users
    print("Creating 10 dummy users...")
    users = [
        ('chris_hemsworth', 'chris.h@example.com', 'password123', 'Chris', 'Hemsworth', '555-0101'), ('zendaya', 'zendaya.c@example.com', 'password456', 'Zendaya', 'Coleman', '555-0102'), ('ryan_reynolds', 'ryan.r@example.com', 'password789', 'Ryan', 'Reynolds', '555-0103'), ('taylor_swift', 'taylor.s@example.com', 'password101', 'Taylor', 'Swift', '555-0104'), ('dwayne_johnson', 'dwayne.j@example.com', 'password112', 'Dwayne', 'Johnson', '555-0105'), ('tom_holland', 'tom.h@example.com', 'password113', 'Tom', 'Holland', '555-0106'), ('scarlett_johansson', 'scarlett.j@example.com', 'password114', 'Scarlett', 'Johansson', '555-0107'), ('keanu_reeves', 'keanu.r@example.com', 'password115', 'Keanu', 'Reeves', '555-0108'), ('margot_robbie', 'margot.r@example.com', 'password116', 'Margot', 'Robbie', '555-0109'), ('idris_elba', 'idris.e@example.com', 'password117', 'Idris', 'Elba', '555-0110')
    ]
    for i, user in enumerate(users):
        user_id = i + 1
        cursor.execute("SELECT id FROM users WHERE username = ?", (user[0],))
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO users (username, email, password_hash, first_name, last_name, phone) VALUES (?, ?, ?, ?, ?, ?)", (user[0], user[1], generate_password_hash(user[2]), user[3], user[4], user[5]))
            cursor.execute("INSERT INTO addresses (user_id, address, city, state, zip_code, is_default) VALUES (?, ?, ?, ?, ?, ?)", (user_id, f'{123+i} Main St', 'Anytown', 'CA', f'123{i:02}', 1))
    print(f"{len(users)} dummy users and their default addresses created.")

    # Populate reviews
    print("Creating a large set of sample reviews...")
    all_sample_reviews = [
        (1, 5, "Absolutely fantastic t-shirt! The fit is perfect and the fabric is incredibly soft. A must-buy."), (1, 5, "My new favorite daily wear tee. Great print quality and doesn't shrink in the wash."), (1, 4, "Solid everyday shirt, the black color holds up well."), (2, 5, "Super comfortable and stylish. Excellent casual wear."), (2, 4, "Good material, relaxed fit is true to size."), (3, 5, "Love the minimalist design on this. The white is crisp and the fit is perfect for a relaxed look."), (3, 4, "Great quality tee, feels premium."), (4, 5, "Perfect basic T. Aura Basics lives up to its name. Five stars for simplicity and quality."), (4, 5, "Soft, great layering piece. Buying more colors."), (4, 5, "The slim fit is just right, not too restrictive."), (4, 4, "Great value for money. Highly recommend this staple."), (5, 5, "Classic polo that you can dress up or down. The navy blue is rich and the fabric has a nice texture."), (5, 4, "A sharp polo that works for the office or a casual weekend. Fit is very comfortable."), (6, 4, "A very clean and crisp white polo. The slim fit is modern and looks great."), (7, 5, "Amazing quality. Looks much more expensive than it is."), (7, 5, "Breathable and stylish. Perfect for warm weather."), (8, 4, "The essential white formal shirt. It's a bit stiff at first, but softens up after a wash. Great for the price."), (9, 5, "The charcoal grey is a versatile color. This henley is my new go-to for a smart-casual look."), (10, 4, "Very comfortable henley, nice olive color that's a bit different from the usual."), (11, 5, "Great for the gym. Breathes well and doesn't restrict movement at all."), (13, 5, "Excellent quality knit sweater, feels very premium and warm."), (14, 4, "A solid V-neck sweater. Good for layering over a shirt for the office."), (15, 5, "Warm, cozy, and the logo is subtle enough. Great for weekend lounging."), (16, 5, "Can't go wrong with a classic grey sweatshirt. This one is super soft inside."), (17, 3, "The colors are great, but the flannel is a bit thinner than I expected."), (18, 5, "Perfect linen shirt for a beach vacation. Lightweight and kept me cool."), (21, 5, "Best jeans I've bought in years. The dark wash is perfect and they have the perfect stretch."), (21, 4, "Stylish and comfortable. My go-to denim."), (21, 5, "Unbelievable fit. Feels custom-made."), (22, 3, "Decent quality, but the straight fit is a little baggier than I expected."), (23, 5, "Aura Denim nails it. These black jeans are a wardrobe staple. They don't fade after washing."), (24, 5, "Classic khaki chinos. The fit is perfect - not too tight, not too loose. Great for any occasion."), (26, 5, "The ultimate work-from-home pants. Soft interior and they look presentable for a coffee run."), (26, 5, "Incredible comfort. They wash and dry quickly without fading."), (26, 5, "Fantastic joggers, better than the big athletic brands."), (27, 5, "Best black joggers, super versatile and stylish for a sporty look."), (29, 4, "These are sharp. The tailored fit on these trousers is excellent. Aura Luxe is impressive."), (30, 4, "Good quality denim shorts, perfect for summer weekends."), (32, 5, "The moisture-wicking on these shorts is legit. Great for running or intense workouts."), (34, 4, "Very comfortable sweatpants for lounging around the house."), (35, 5, "A timeless piece. The blue wash is exactly what I was looking for. Perfect layering weight."), (35, 5, "This jacket feels like it will last a decade. Excellent craftsmanship from Aura Denim."), (35, 4, "Great jacket, slightly stiff but I expect it to break in nicely."), (36, 4, "Stylish and warm enough for a cool evening. Good slim profile."), (37, 2, "Looked great but the leather felt a bit stiff and the fit was too tight in the shoulders for me."), (39, 4, "Warm puffer jacket, great for winter commutes."), (40, 5, "Super soft interior fleece. My favorite hoodie now."), (41, 5, "A classic black hoodie. Can't go wrong. The material feels durable."), (42, 5, "Sharp fit. Aura Luxe delivered a perfect business-casual piece."), (43, 3, "It's a good compression shirt, but a bit restrictive for my workouts."), (45, 5, "Moisture-wicking works perfectly. Stays dry even during intense sessions."), (45, 5, "Lightest tank I own. Zero chafing."), (45, 5, "Perfect for the gym. The fit is athletic but comfortable."), (47, 4, "Sleek track jacket. Good for a morning run or just as a light layer."), (49, 5, "Great compression and support for leg day. Aura Active is top-notch."), (50, 4, "Good for lifting weights. Keeps me warm without overheating."),
    ]
    for i, review in enumerate(all_sample_reviews):
        user_id_to_use = random.randint(1, len(users))
        review_date = (datetime.now() - timedelta(days=i * random.randint(1, 5))).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO reviews (product_id, user_id, rating, comment, review_date) VALUES (?, ?, ?, ?, ?)", (review[0], user_id_to_use, review[1], review[2], review_date))
    print(f"{len(all_sample_reviews)} sample reviews created.")

    # Calculate and update ratings
    print("Calculating and updating average ratings and counts...")
    product_ids_with_reviews = cursor.execute("SELECT DISTINCT product_id FROM reviews").fetchall()
    for row in product_ids_with_reviews:
        product_id = row['product_id']
        stats_data = cursor.execute("SELECT AVG(rating) as avg_rating, COUNT(id) as rating_count FROM reviews WHERE product_id = ?", (product_id,)).fetchone()
        if stats_data:
            avg_rating = round(stats_data['avg_rating'], 1) if stats_data['avg_rating'] else 0
            rating_count = stats_data['rating_count']
            cursor.execute("UPDATE products SET rating = ?, num_ratings = ? WHERE id = ?", (avg_rating, rating_count, product_id))
    print("Ratings updated.")

    # CALL TO THE DEDICATED TEST USER FUNCTION
    create_dedicated_test_user(cursor)
            
    conn.commit()
    conn.close()
    print("Database setup complete and connection closed.")

if __name__ == '__main__':
    setup_database()