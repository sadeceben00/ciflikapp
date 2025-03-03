from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime
import random

app = Flask(__name__)
app.secret_key = 'supersecretkey'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Veritabanı Kurulumu
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, price REAL, stock REAL, image TEXT, seller_id INTEGER, category TEXT, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders 
                 (id INTEGER PRIMARY KEY, product_name TEXT, price REAL, kg REAL, 
                  buyer_id INTEGER, seller_id INTEGER, sale_date TEXT, status TEXT, tracking_code TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, 
                  full_name TEXT, address TEXT, balance REAL DEFAULT 0, email TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reviews 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, user_id INTEGER, rating INTEGER, comment TEXT, date TEXT)''')
    conn.commit()
    conn.close()

# Klasör Oluşturma
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Giriş Gerektiren Sayfalar için Dekoratör
def login_required(role=None):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('user_id') == 0 and session.get('role') == 'admin':
                return f(*args, **kwargs)
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            c.execute("SELECT role FROM users WHERE id = ?", (session['user_id'],))
            result = c.fetchone()
            conn.close()
            if not result:
                flash("Kullanıcı bulunamadı!")
                return redirect(url_for('index'))
            user_role = result[0]
            if role is None or user_role == role or user_role == 'admin':
                return f(*args, **kwargs)
            flash("Bu sayfaya erişim yetkiniz yok!")
            return redirect(url_for('index'))
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# Ana Sayfa
@app.route('/')
def index():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE stock > 0 ORDER BY RANDOM() LIMIT 6")
    featured_products = c.fetchall()
    conn.close()
    return render_template('index.html', featured_products=featured_products)

# Kayıt Sayfası
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        full_name = request.form['full_name']
        address = request.form['address']
        email = request.form['email']
        if role not in ['alici', 'satici']:
            flash("Geçersiz rol!")
            return redirect(url_for('register'))
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, role, full_name, address, email) VALUES (?, ?, ?, ?, ?, ?)", 
                      (username, password, role, full_name, address, email))
            conn.commit()
            flash("Kayıt başarılı! Giriş yapabilirsiniz.")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Bu kullanıcı adı zaten alınmış!")
        conn.close()
    return render_template('register.html')

# Giriş Sayfası
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin':
            session['user_id'] = 0
            session['role'] = 'admin'
            flash("Yönetici olarak giriş yaptınız.")
            return redirect(url_for('admin'))
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT id, role FROM users WHERE username = ? AND password = ?", 
                  (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['role'] = user[1]
            flash("Giriş başarılı!")
            if user[1] == 'alici':
                return redirect(url_for('buyer'))
            elif user[1] == 'satici':
                return redirect(url_for('seller'))
        else:
            flash("Geçersiz kullanıcı adı veya şifre!")
    return render_template('login.html')

# Çıkış Yapma
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("Çıkış yaptınız.")
    return redirect(url_for('index'))

# Profil Sayfası
@app.route('/profile', methods=['GET', 'POST'])
@login_required()
def profile():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        full_name = request.form['full_name']
        address = request.form['address']
        email = request.form['email']
        c.execute("UPDATE users SET full_name = ?, address = ?, email = ? WHERE id = ?", 
                  (full_name, address, email, session['user_id']))
        conn.commit()
        flash("Profil güncellendi!")
    
    if session['user_id'] == 0:
        user = ('admin', 'Admin Kullanıcı', 'Yönetim Merkezi', 0, 'admin', 'admin@tazepazar.com')
    else:
        c.execute("SELECT username, full_name, address, balance, role, email FROM users WHERE id = ?", (session['user_id'],))
        user = c.fetchone()
    conn.close()
    return render_template('profile.html', user=user)

# Alıcı Sayfası
@app.route('/buyer', methods=['GET', 'POST'])
@login_required('alici')
def buyer():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        if 'add_to_cart' in request.form:
            product_id = request.form['product_id']
            kg = float(request.form['kg'])
            buyer_id = session['user_id']
            c.execute("SELECT name, price, stock, seller_id FROM products WHERE id = ?", (product_id,))
            product = c.fetchone()
            if product and product[2] >= kg:
                total_price = product[1] * kg
                sale_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                tracking_code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
                c.execute("INSERT INTO orders (product_name, price, kg, buyer_id, seller_id, sale_date, status, tracking_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                          (product[0], total_price, kg, buyer_id, product[3], sale_date, 'pending', tracking_code))
                c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (kg, product_id))
                conn.commit()
                flash(f"Ürün sepete eklendi! Takip Kodu: {tracking_code}")
            else:
                flash("Yetersiz stok veya geçersiz miktar!")
        elif 'pay' in request.form:
            order_id = request.form['order_id']
            c.execute("SELECT price FROM orders WHERE id = ? AND buyer_id = ?", (order_id, session['user_id']))
            order = c.fetchone()
            if order:
                total_price = order[0]
                c.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
                balance = c.fetchone()[0]
                if balance >= total_price:
                    c.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (total_price, session['user_id']))
                    c.execute("UPDATE users SET balance = balance + ? WHERE id = (SELECT seller_id FROM orders WHERE id = ?)", 
                              (total_price, order_id))
                    c.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
                    conn.commit()
                    flash("Ödeme başarılı! Siparişiniz kargoya verildi.")
                else:
                    flash("Yetersiz bakiye!")
        elif 'add_review' in request.form:
            product_id = request.form['product_id']
            rating = int(request.form['rating'])
            comment = request.form['comment']
            date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute("INSERT INTO reviews (product_id, user_id, rating, comment, date) VALUES (?, ?, ?, ?, ?)", 
                      (product_id, session['user_id'], rating, comment, date))
            conn.commit()
            flash("Yorumunuz eklendi!")

    search_query = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    query = "SELECT * FROM products WHERE stock > 0"
    params = []
    if search_query:
        query += " AND name LIKE ?"
        params.append(f'%{search_query}%')
    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)
    c.execute(query, params)
    products = c.fetchall()
    
    c.execute("SELECT * FROM orders WHERE buyer_id = ? AND status = 'pending'", (session['user_id'],))
    cart = c.fetchall()
    c.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
    balance = c.fetchone()[0]
    c.execute("SELECT o.*, p.description FROM orders o JOIN products p ON o.product_name = p.name WHERE o.buyer_id = ?", (session['user_id'],))
    order_history = c.fetchall()
    conn.close()
    return render_template('buyer.html', products=products, cart=cart, balance=balance, order_history=order_history)

# Satıcı Sayfası
@app.route('/seller', methods=['GET', 'POST'])
@login_required('satici')
def seller():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        if 'add_product' in request.form:
            name = request.form['name']
            price = float(request.form['price'])
            stock = float(request.form['stock'])
            category = request.form['category']
            description = request.form['description']
            file = request.files['image']
            image_path = None
            if file and file.filename:
                filename = file.filename
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_path = f'uploads/{filename}'
            seller_id = session['user_id']
            c.execute("INSERT INTO products (name, price, stock, image, seller_id, category, description) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                      (name, price, stock, image_path, seller_id, category, description))
            conn.commit()
            flash("Ürün eklendi!")
        elif 'delete_product' in request.form:
            product_id = request.form['product_id']
            c.execute("DELETE FROM products WHERE id = ? AND seller_id = ?", (product_id, session['user_id']))
            conn.commit()
            flash("Ürün silindi!")
    
    c.execute("SELECT * FROM products WHERE seller_id = ?", (session['user_id'],))
    products = c.fetchall()
    c.execute("SELECT o.*, u.username AS buyer_name FROM orders o JOIN users u ON o.buyer_id = u.id WHERE o.seller_id = ?", (session['user_id'],))
    orders = c.fetchall()
    c.execute("SELECT balance FROM users WHERE id = ?", (session['user_id'],))
    balance = c.fetchone()[0]
    conn.close()
    return render_template('seller.html', products=products, orders=orders, balance=balance)

# Yönetici Sayfası
@app.route('/admin', methods=['GET', 'POST'])
@login_required('admin')
def admin():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        if 'delete_product' in request.form:
            product_id = request.form['product_id']
            c.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()
            flash("Ürün silindi!")
        elif 'add_balance' in request.form:
            user_id = request.form['user_id']
            amount = float(request.form['amount'])
            if amount > 0:
                c.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
                conn.commit()
                flash(f"{amount} TL bakiye eklendi!")
            else:
                flash("Geçersiz miktar!")
        elif 'update_status' in request.form:
            order_id = request.form['order_id']
            status = request.form['status']
            c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
            conn.commit()
            flash("Sipariş durumu güncellendi!")
    
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    c.execute('''SELECT o.id, o.product_name, o.price, o.kg, o.sale_date, o.status, o.tracking_code,
                        ub.username AS buyer_name, us.username AS seller_name
                 FROM orders o
                 LEFT JOIN users ub ON o.buyer_id = ub.id
                 LEFT JOIN users us ON o.seller_id = us.id''')
    order_details = c.fetchall()
    c.execute("SELECT COUNT(*) FROM orders")
    order_count = c.fetchone()[0]
    c.execute("SELECT id, username, full_name, address, balance FROM users WHERE role = 'alici'")
    buyers = c.fetchall()
    c.execute('''SELECT p.id, p.name, r.rating, r.comment, r.date, u.username 
                 FROM reviews r 
                 JOIN products p ON r.product_id = p.id 
                 JOIN users u ON r.user_id = u.id''')
    reviews = c.fetchall()
    conn.close()
    return render_template('admin.html', products=products, order_details=order_details, order_count=order_count, buyers=buyers, reviews=reviews)

# Ürün Detay Sayfası
@app.route('/product/<int:product_id>', methods=['GET', 'POST'])
@login_required()
def product_detail(product_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    product = c.fetchone()
    c.execute('''SELECT r.rating, r.comment, r.date, u.username 
                 FROM reviews r 
                 JOIN users u ON r.user_id = u.id 
                 WHERE r.product_id = ?''', (product_id,))
    reviews = c.fetchall()
    conn.close()
    return render_template('product_detail.html', product=product, reviews=reviews)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)