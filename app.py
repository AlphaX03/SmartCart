from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
import os
import math

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    app.logger.warning("SECRET_KEY is not set. Set a strong SECRET_KEY in your .env file.")


def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD")
        )
    except (Error, TypeError, ValueError) as e:
        app.logger.exception("Database connection error: %s", e)
        return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session or "store_id" not in session:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def get_store_settings(cursor):
    """Return settings for the currently authenticated store."""
    cursor.execute(
        """SELECT id, store_name, store_address, phone, email, currency,
                  low_stock_threshold
           FROM settings WHERE store_id = %s LIMIT 1""",
        (session["store_id"],)
    )
    settings_data = cursor.fetchone()
    if settings_data:
        return settings_data

    cursor.execute("SELECT store_name FROM stores WHERE id = %s", (session["store_id"],))
    store = cursor.fetchone()
    name = store["store_name"] if store else "My Store"
    return {
        "id": None, "store_name": name, "store_address": "", "phone": "",
        "email": "", "currency": "₹", "low_stock_threshold": 5
    }


@app.route("/")
def home():
    if "user_id" in session and "store_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        connection = get_db_connection()
        if connection is None:
            return render_template("login.html", error="Unable to connect to the database."), 500

        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """SELECT id, username, password_hash, role, store_id
                   FROM users WHERE username = %s LIMIT 1""",
                (username,)
            )
            user = cursor.fetchone()
            if user and user["store_id"] is not None and check_password_hash(user["password_hash"], password):
                cursor.execute("SELECT id FROM stores WHERE id = %s", (user["store_id"],))
                if cursor.fetchone():
                    session.clear()
                    session["user_id"] = user["id"]
                    session["username"] = user["username"]
                    session["role"] = user["role"]
                    session["store_id"] = user["store_id"]
                    return redirect(url_for("dashboard"))
            return render_template("login.html", error="Invalid username or password."), 401
        finally:
            cursor.close()
            connection.close()
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    store_name = (request.form.get("store_name") or "").strip()
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    if not store_name or not username or not password:
        return render_template("register.html", error="Please complete all required fields."), 400
    if len(store_name) > 100 or len(username) > 50:
        return render_template("register.html", error="Store name or username is too long."), 400
    if len(password) < 8:
        return render_template("register.html", error="Password must contain at least 8 characters."), 400
    if password != confirm_password:
        return render_template("register.html", error="The passwords do not match."), 400

    connection = get_db_connection()
    if connection is None:
        return render_template("register.html", error="Unable to connect to the database."), 500
    cursor = connection.cursor()
    try:
        connection.start_transaction()
        cursor.execute("INSERT INTO stores (store_name) VALUES (%s)", (store_name,))
        store_id = cursor.lastrowid
        cursor.execute(
            """INSERT INTO users (username, password_hash, role, store_id)
               VALUES (%s, %s, %s, %s)""",
            (username, generate_password_hash(password), "admin", store_id)
        )
        cursor.execute(
            """INSERT INTO settings
               (store_name, store_address, phone, email, currency, low_stock_threshold, store_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (store_name, "", "", "", "₹", 5, store_id)
        )
        connection.commit()
        return redirect(url_for("login"))
    except mysql.connector.IntegrityError as e:
        connection.rollback()
        app.logger.warning("Store registration constraint error: %s", e)
        return render_template("register.html", error="That username is already registered."), 409
    except Error:
        connection.rollback()
        app.logger.exception("Store registration failed")
        return render_template("register.html", error="Registration failed. Check the Flask terminal."), 500
    finally:
        cursor.close()
        connection.close()


@app.route("/dashboard")
@login_required
def dashboard():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        cursor.execute(
            """SELECT COALESCE(SUM(total_amount), 0) AS today_sales, COUNT(*) AS today_orders
               FROM bills WHERE store_id = %s AND DATE(created_at) = CURDATE()""",
            (store_id,)
        )
        today = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) AS total_products FROM products WHERE store_id = %s", (store_id,))
        products_summary = cursor.fetchone()
        cursor.execute(
            """SELECT DATE(created_at) AS sale_date,
                      COALESCE(SUM(total_amount), 0) AS daily_sales
               FROM bills WHERE store_id = %s
                 AND DATE(created_at) >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
               GROUP BY DATE(created_at) ORDER BY sale_date ASC""",
            (store_id,)
        )
        sales_overview = cursor.fetchall()
        settings_data = get_store_settings(cursor)
        return render_template(
            "dashboard.html", username=session["username"],
            store_name=settings_data["store_name"],
            today_sales=today["today_sales"], today_orders=today["today_orders"],
            total_products=products_summary["total_products"], sales_overview=sales_overview
        )
    except Error:
        app.logger.exception("Dashboard error")
        return "Unable to load dashboard", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/inventory")
@login_required
def inventory():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        settings_data = get_store_settings(cursor)
        threshold = settings_data["low_stock_threshold"] or 5
        cursor.execute(
            """SELECT COUNT(*) AS total_products,
                      COALESCE(SUM(stock_quantity), 0) AS total_stock_units,
                      COALESCE(SUM(CASE WHEN stock_quantity > 0 AND stock_quantity <= %s THEN 1 ELSE 0 END), 0) AS low_stock_products,
                      COALESCE(SUM(CASE WHEN stock_quantity <= 0 THEN 1 ELSE 0 END), 0) AS out_of_stock_products
               FROM products WHERE store_id = %s""",
            (threshold, store_id)
        )
        inventory_summary = cursor.fetchone()
        cursor.execute(
            """SELECT id, product_name, category, price, stock_quantity, unit, barcode
               FROM products WHERE store_id = %s
               ORDER BY CASE WHEN stock_quantity <= 0 THEN 0
                             WHEN stock_quantity <= %s THEN 1 ELSE 2 END,
                        product_name ASC""",
            (store_id, threshold)
        )
        inventory_products = cursor.fetchall()
        return render_template(
            "inventory.html", username=session["username"],
            inventory_summary=inventory_summary, inventory_products=inventory_products,
            low_stock_threshold=threshold
        )
    except Error:
        app.logger.exception("Inventory error")
        return "Unable to load inventory", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/products")
@login_required
def products():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        settings_data = get_store_settings(cursor)
        threshold = settings_data["low_stock_threshold"] or 5
        cursor.execute(
            """SELECT COUNT(*) AS total_products,
                      COALESCE(SUM(stock_quantity), 0) AS total_stock_units,
                      COALESCE(SUM(CASE WHEN stock_quantity > 0 AND stock_quantity <= %s THEN 1 ELSE 0 END), 0) AS low_stock_products,
                      COALESCE(SUM(CASE WHEN stock_quantity <= 0 THEN 1 ELSE 0 END), 0) AS out_of_stock_products
               FROM products WHERE store_id = %s""",
            (threshold, store_id)
        )
        inventory_summary = cursor.fetchone()
        cursor.execute(
            """SELECT id, product_name, category, price, stock_quantity, unit, barcode
               FROM products WHERE store_id = %s ORDER BY product_name ASC""",
            (store_id,)
        )
        products_list = cursor.fetchall()
        # Preserve the variable expected by the existing products template.
        return render_template(
            "products.html", username=session["username"], products=products_list,
            inventory_summary=inventory_summary, low_stock_threshold=threshold
        )
    except Error:
        app.logger.exception("Products error")
        return "Unable to load products", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/products/add", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "GET":
        return render_template("add_product.html")
    product_name = (request.form.get("product_name") or "").strip()
    category = (request.form.get("category") or "").strip()
    price_raw = request.form.get("price")
    stock_raw = request.form.get("stock_quantity")
    unit = (request.form.get("unit") or "").strip()
    barcode = (request.form.get("barcode") or "").strip() or None

    try:
        price = Decimal(str(price_raw))
        stock = Decimal(str(stock_raw))
        if not price.is_finite() or price < 0:
            raise ValueError
        if not stock.is_finite() or stock < 0:
            raise ValueError
        if not product_name or not unit:
            raise ValueError
    except (InvalidOperation, TypeError, ValueError):
        return render_template("add_product.html", error="Enter a valid product name, price, stock quantity, and unit."), 400

    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor()
    try:
        cursor.execute(
            """INSERT INTO products
               (product_name, category, price, stock_quantity, unit, barcode, store_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (product_name, category, price, stock, unit, barcode, session["store_id"])
        )
        connection.commit()
        return redirect(url_for("products"))
    except mysql.connector.IntegrityError:
        connection.rollback()
        return render_template("add_product.html", error="Barcode already exists."), 409
    except Error:
        connection.rollback()
        app.logger.exception("Add product error")
        return "Unable to add product", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        cursor.execute("SELECT * FROM products WHERE id = %s AND store_id = %s", (product_id, store_id))
        product = cursor.fetchone()
        if product is None:
            return "Product not found", 404

        if request.method == "GET":
            return render_template("edit_product.html", product=product)

        product_name = (request.form.get("product_name") or "").strip()
        category = (request.form.get("category") or "").strip()
        price_raw = request.form.get("price")
        stock_raw = request.form.get("stock_quantity")
        unit = (request.form.get("unit") or "").strip()
        barcode = (request.form.get("barcode") or "").strip() or None
        try:
            price = Decimal(str(price_raw))
            stock = Decimal(str(stock_raw))
            if not price.is_finite() or price < 0 or not stock.is_finite() or stock < 0:
                raise ValueError
            if not product_name or not unit:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            return render_template("edit_product.html", product=product, error="Enter valid product details and a non-negative stock quantity."), 400

        cursor.execute(
            """UPDATE products SET product_name=%s, category=%s, price=%s,
                      stock_quantity=%s, unit=%s, barcode=%s
               WHERE id=%s AND store_id=%s""",
            (product_name, category, price, stock, unit, barcode, product_id, store_id)
        )
        connection.commit()
        return redirect(url_for("products"))
    except mysql.connector.IntegrityError:
        connection.rollback()
        return render_template("edit_product.html", product=product, error="Barcode already exists."), 409
    except Error:
        connection.rollback()
        app.logger.exception("Edit product error")
        return "Unable to update product", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/products/delete/<int:product_id>", methods=["GET", "POST"])
@login_required
def delete_product(product_id):
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM products WHERE id = %s AND store_id = %s", (product_id, session["store_id"]))
        connection.commit()
        if cursor.rowcount == 0:
            return "Product not found", 404
        return redirect(url_for("products"))
    except Error:
        connection.rollback()
        app.logger.exception("Delete product error")
        return "Unable to delete product", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/billing")
@login_required
def billing():
    return render_template("billing.html", username=session["username"])


@app.route("/billing/search")
@login_required
def search_products():
    search = (request.args.get("q") or "").strip()
    if not search:
        return []
    connection = get_db_connection()
    if connection is None:
        return {"error": "Database connection failed"}, 500
    cursor = connection.cursor(dictionary=True)
    try:
        pattern = f"%{search}%"
        cursor.execute(
            """SELECT id, product_name, category, price, stock_quantity, unit, barcode
               FROM products
               WHERE store_id = %s AND (product_name LIKE %s OR barcode LIKE %s)
               ORDER BY product_name LIMIT 20""",
            (session["store_id"], pattern, pattern)
        )
        return cursor.fetchall()
    except Error:
        app.logger.exception("Product search error")
        return {"error": "Unable to search products"}, 500
    finally:
        cursor.close()
        connection.close()


@app.route("/billing/create", methods=["POST"])
@login_required
def create_bill():
    data = request.get_json(silent=True)
    if not data:
        return {"success": False, "message": "No bill data received."}, 400
    customer_name = (data.get("customer_name") or "").strip()
    cart = data.get("cart") or []
    payment_method = data.get("payment_method", "Cash")
    if payment_method not in {"Cash", "Card", "UPI", "Online"}:
        payment_method = "Cash"
    if not cart:
        return {"success": False, "message": "Cart is empty."}, 400

    connection = get_db_connection()
    if connection is None:
        return {"success": False, "message": "Database connection failed."}, 500
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        connection.start_transaction()
        store_id = session["store_id"]
        subtotal = Decimal("0.00")
        validated_items = []

        for item in cart:
            product_id = item.get("id")
            requested_quantity = item.get("quantity")
            if not product_id or requested_quantity is None:
                raise ValueError("Invalid product information.")
            try:
                quantity = Decimal(str(requested_quantity))
                if not quantity.is_finite() or quantity <= 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError("Please enter a valid quantity greater than zero.")

            cursor.execute(
                """SELECT id, product_name, price, stock_quantity, unit
                   FROM products WHERE id = %s AND store_id = %s FOR UPDATE""",
                (product_id, store_id)
            )
            product = cursor.fetchone()
            if product is None:
                raise ValueError(f"Product with ID {product_id} was not found in your store.")
            available = Decimal(str(product["stock_quantity"]))
            if quantity > available:
                raise ValueError(
                    f"Insufficient stock for {product['product_name']}. Available stock: {available}."
                )
            price = Decimal(str(product["price"]))
            line_total = (price * quantity).quantize(Decimal("0.01"))
            subtotal += line_total
            validated_items.append({
                "product_id": product["id"], "product_name": product["product_name"],
                "quantity": quantity, "price": price, "total": line_total, "unit": product["unit"]
            })

        # Timestamp-based number is globally unique-compatible with the existing UNIQUE index.
        bill_number = f"SC-{store_id}-{datetime.now().strftime('%y%m%d%H%M%S%f')}"
        payment_time = datetime.now()
        payment_status = "Pending" if payment_method == "Online" else "Paid"
        payment_date = payment_time

        cursor.execute(
            """INSERT INTO bills
               (bill_number, customer_name, subtotal, total_amount, payment_status,
                payment_method, transaction_id, payment_date, store_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (bill_number, customer_name or None, subtotal, subtotal, payment_status,
             payment_method, None, payment_date, store_id)
        )
        bill_id = cursor.lastrowid

        for item in validated_items:
            cursor.execute(
                """INSERT INTO bill_items
                   (bill_id, product_id, product_name, quantity, price, total, unit)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (bill_id, item["product_id"], item["product_name"], item["quantity"],
                 item["price"], item["total"], item["unit"])
            )
            cursor.execute(
                """UPDATE products SET stock_quantity = stock_quantity - %s
                   WHERE id = %s AND store_id = %s""",
                (item["quantity"], item["product_id"], store_id)
            )
            if cursor.rowcount != 1:
                raise ValueError("A product could not be updated for this store.")

        connection.commit()
        return {
            "success": True, "message": "Bill created successfully.",
            "bill_id": bill_id, "bill_number": bill_number,
            "subtotal": float(subtotal), "total": float(subtotal),
            "payment_method": payment_method, "payment_status": payment_status
        }
    except ValueError as e:
        connection.rollback()
        return {"success": False, "message": str(e)}, 400
    except Error:
        connection.rollback()
        app.logger.exception("Bill creation database error")
        return {"success": False, "message": "Database error while creating bill."}, 500
    except Exception:
        connection.rollback()
        app.logger.exception("Unexpected bill creation error")
        return {"success": False, "message": "Unable to create bill."}, 500
    finally:
        if cursor:
            cursor.close()
        connection.close()


@app.route("/billing/receipt/<int:bill_id>")
@login_required
def bill_receipt(bill_id):
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        cursor.execute(
            """SELECT id, bill_number, customer_name, subtotal, total_amount,
                      payment_status, payment_method, transaction_id, payment_date, created_at
               FROM bills WHERE id = %s AND store_id = %s""",
            (bill_id, store_id)
        )
        bill = cursor.fetchone()
        if bill is None:
            return "Bill not found", 404
        cursor.execute(
            """SELECT product_name, quantity, price, total, unit
               FROM bill_items WHERE bill_id = %s ORDER BY id""",
            (bill_id,)
        )
        items = cursor.fetchall()
        settings_data = get_store_settings(cursor)
        return render_template(
            "bill_receipt.html", bill=bill, items=items,
            store_name=settings_data["store_name"],
            settings=settings_data
        )
    except Error:
        app.logger.exception("Receipt error")
        return "Unable to load bill receipt", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/billing/history")
@login_required
def billing_history():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        date_filter = request.args.get("filter", "all")
        date_conditions = {
            "today": "AND DATE(created_at) = CURDATE()",
            "week": "AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)",
            "month": "AND YEAR(created_at) = YEAR(CURDATE()) AND MONTH(created_at) = MONTH(CURDATE())"
        }
        condition = date_conditions.get(date_filter, "")
        cursor.execute(
            f"""SELECT id, bill_number, customer_name, subtotal, total_amount,
                       payment_status, payment_method, transaction_id, payment_date, created_at
                FROM bills WHERE store_id = %s {condition} ORDER BY id DESC""",
            (session["store_id"],)
        )
        bills = cursor.fetchall()
        total_bills = len(bills)
        total_sales = sum(float(b["total_amount"]) for b in bills)
        average_bill = total_sales / total_bills if total_bills else 0
        return render_template(
            "billing_history.html", bills=bills, total_bills=total_bills,
            total_sales=total_sales, average_bill=average_bill, current_filter=date_filter
        )
    except Error:
        app.logger.exception("Billing history error")
        return "Unable to load billing history", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/sales")
@login_required
def sales():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        cursor.execute(
            """SELECT COALESCE(SUM(total_amount), 0) AS total_sales, COUNT(*) AS total_bills
               FROM bills WHERE store_id = %s AND DATE(created_at) = CURDATE()""", (store_id,)
        )
        today_summary = cursor.fetchone()
        cursor.execute(
            """SELECT COALESCE(SUM(total_amount), 0) AS total_sales, COUNT(*) AS total_bills
               FROM bills WHERE store_id = %s AND YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)""",
            (store_id,)
        )
        week_summary = cursor.fetchone()
        cursor.execute(
            """SELECT COALESCE(SUM(total_amount), 0) AS total_sales, COUNT(*) AS total_bills
               FROM bills WHERE store_id = %s AND YEAR(created_at) = YEAR(CURDATE())
               AND MONTH(created_at) = MONTH(CURDATE())""", (store_id,)
        )
        month_summary = cursor.fetchone()
        cursor.execute(
            "SELECT COALESCE(SUM(total_amount), 0) AS total_sales, COUNT(*) AS total_bills FROM bills WHERE store_id = %s",
            (store_id,)
        )
        overall_summary = cursor.fetchone()
        cursor.execute(
            """SELECT DATE(created_at) AS sale_date, COALESCE(SUM(total_amount), 0) AS daily_sales
               FROM bills WHERE store_id = %s
               AND DATE(created_at) >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
               GROUP BY DATE(created_at) ORDER BY sale_date ASC""", (store_id,)
        )
        daily_sales = cursor.fetchall()
        return render_template(
            "sales.html", today_summary=today_summary, week_summary=week_summary,
            month_summary=month_summary, overall_summary=overall_summary, daily_sales=daily_sales
        )
    except Error:
        app.logger.exception("Sales error")
        return "Unable to load sales data", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/reports")
@login_required
def reports():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        cursor.execute(
            """SELECT COALESCE(SUM(total_amount), 0) AS total_sales, COUNT(*) AS total_bills
               FROM bills WHERE store_id = %s""", (store_id,)
        )
        summary = cursor.fetchone()
        average_bill = float(summary["total_sales"]) / summary["total_bills"] if summary["total_bills"] else 0
        cursor.execute(
            """SELECT bi.product_name, SUM(bi.quantity) AS quantity_sold, SUM(bi.total) AS revenue
               FROM bill_items bi
               INNER JOIN bills b ON b.id = bi.bill_id
               WHERE b.store_id = %s
               GROUP BY bi.product_id, bi.product_name ORDER BY revenue DESC""",
            (store_id,)
        )
        product_sales = cursor.fetchall()
        top_products = product_sales[:5]
        cursor.execute(
            """SELECT DATE(created_at) AS sale_date, COALESCE(SUM(total_amount), 0) AS daily_sales
               FROM bills WHERE store_id = %s
               GROUP BY DATE(created_at) ORDER BY sale_date ASC""", (store_id,)
        )
        daily_sales = cursor.fetchall()
        return render_template(
            "reports.html", summary=summary, average_bill=average_bill,
            product_sales=product_sales, top_products=top_products, daily_sales=daily_sales
        )
    except Error:
        app.logger.exception("Reports error")
        return "Unable to load reports", 500
    finally:
        cursor.close()
        connection.close()


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    connection = get_db_connection()
    if connection is None:
        return "Database connection failed", 500
    cursor = connection.cursor(dictionary=True)
    try:
        store_id = session["store_id"]
        if request.method == "POST":
            store_name = (request.form.get("store_name") or "").strip()
            store_address = (request.form.get("store_address") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            email = (request.form.get("email") or "").strip()
            currency = (request.form.get("currency") or "₹").strip()
            try:
                threshold = int(request.form.get("low_stock_threshold", 5))
                if threshold < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return "Low stock threshold must be a non-negative whole number.", 400
            if not store_name or len(store_name) > 100:
                return "Please enter a valid store name.", 400

            
            cursor.execute(
                "SELECT id FROM settings WHERE store_id = %s LIMIT 1",
                (store_id,)
            )
            existing_settings = cursor.fetchone()

            if existing_settings:
                cursor.execute(
                    """UPDATE settings
                    SET store_name=%s, store_address=%s, phone=%s,
                        email=%s, currency=%s, low_stock_threshold=%s
                    WHERE store_id=%s""",
                    (
                        store_name, store_address, phone, email,
                        currency, threshold, store_id
                    )
                )
            else:
                cursor.execute(
                    """INSERT INTO settings
                    (store_name, store_address, phone, email,
                        currency, low_stock_threshold, store_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        store_name, store_address, phone, email,
                        currency, threshold, store_id
                    )
                )

            cursor.execute("UPDATE stores SET store_name=%s WHERE id=%s", (store_name, store_id))
            connection.commit()
            return redirect(url_for("settings"))

        settings_data = get_store_settings(cursor)
        return render_template("settings.html", settings=settings_data, username=session["username"])
    except Error:
        connection.rollback()
        app.logger.exception("Settings error")
        return "Unable to load settings", 500
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    app.run(debug=True)
