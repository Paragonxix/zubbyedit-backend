#!/usr/bin/env python3
"""
ZubbyEdit Backend API
Pure Python + SQLite — no external dependencies required.
"""

import json
import sqlite3
import hashlib
import secrets
import time
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

DB_PATH = "zubbyedit.db"
PORT = int(__import__("os").environ.get("PORT", "8000"))

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'buyer',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        icon TEXT,
        slug TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        category_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        price INTEGER NOT NULL,
        delivery TEXT DEFAULT '2 days',
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_id) REFERENCES users(id),
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );

    CREATE TABLE IF NOT EXISTS verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        proof TEXT,
        why TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer_id INTEGER NOT NULL,
        seller_id INTEGER,
        listing_id INTEGER,
        service_title TEXT NOT NULL,
        seller_name TEXT,
        price INTEGER NOT NULL,
        base_price INTEGER,
        brief TEXT,
        status TEXT DEFAULT 'in_progress',
        delivery_file TEXT,
        delivery_note TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (buyer_id) REFERENCES users(id),
        FOREIGN KEY (seller_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT NOT NULL,
        sender_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sender_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS wallet_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        title TEXT,
        amount INTEGER NOT NULL,
        status TEXT DEFAULT 'completed',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS wallets (
        user_id INTEGER PRIMARY KEY,
        available INTEGER DEFAULT 0,
        pending INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # Seed categories
    cats = [
        ("Video Editing", "🎬", "editing"),
        ("Media Growth", "📈", "growth"),
        ("Graphic Design", "🎨", "design"),
        ("Copywriting", "✍️", "copy"),
        ("Photography", "📸", "photo"),
        ("Voice-over / Audio", "🎙️", "audio"),
        ("Content Strategy", "🧠", "strategy"),
    ]
    for name, icon, slug in cats:
        c.execute(
            "INSERT OR IGNORE INTO categories (name, icon, slug) VALUES (?, ?, ?)",
            (name, icon, slug)
        )

    # Seed demo seller + listings if empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        demo_hash = hash_password("demo1234")
        c.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            ("Tunde Edits", "tunde@zubbyedit.com", "08011112222", demo_hash, "seller")
        )
        tunde_id = c.lastrowid
        c.execute("INSERT INTO wallets (user_id, available, pending) VALUES (?, ?, ?)", (tunde_id, 62000, 18500))

        c.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            ("Amaka Designs", "amaka@zubbyedit.com", "08033334444", demo_hash, "seller")
        )
        amaka_id = c.lastrowid
        c.execute("INSERT INTO wallets (user_id, available, pending) VALUES (?, ?, ?)", (amaka_id, 31000, 5000))

        # Demo buyer
        c.execute(
            "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            ("Demo User", "demo@zubbyedit.com", "08055556666", demo_hash, "buyer")
        )
        demo_id = c.lastrowid
        c.execute("INSERT INTO wallets (user_id, available, pending) VALUES (?, ?, ?)", (demo_id, 0, 0))

        # Listings
        c.execute("SELECT id FROM categories WHERE slug='editing'")
        edit_cat = c.fetchone()["id"]
        c.execute("SELECT id FROM categories WHERE slug='design'")
        design_cat = c.fetchone()["id"]
        c.execute("SELECT id FROM categories WHERE slug='growth'")
        growth_cat = c.fetchone()["id"]
        c.execute("SELECT id FROM categories WHERE slug='copy'")
        copy_cat = c.fetchone()["id"]

        listings = [
            (tunde_id, edit_cat, "Professional Reels & TikTok Editing",
             "High-quality short-form editing with trending audio, captions, transitions and effects.",
             12000, "1–2 days"),
            (amaka_id, design_cat, "YouTube Thumbnail Design (3 concepts)",
             "Eye-catching YouTube thumbnails that increase click-through rate.",
             5000, "24 hours"),
            (tunde_id, growth_cat, "Instagram Growth Package – 5k Followers",
             "Organic-looking Instagram follower growth. Gradual delivery.",
             25000, "3–7 days"),
            (amaka_id, copy_cat, "Viral Script + Hook Writing",
             "Scroll-stopping hooks and full scripts for Reels, TikTok and Shorts.",
             8000, "1 day"),
        ]
        for lid, cid, title, desc, price, delivery in listings:
            c.execute(
                """INSERT INTO listings (seller_id, category_id, title, description, price, delivery)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (lid, cid, title, desc, price, delivery)
            )

        # Sample verification requests
        c.execute(
            """INSERT INTO verifications (user_id, category, proof, why, status)
               VALUES (?, ?, ?, ?, ?)""",
            (amaka_id, "Graphic Design",
             "Instagram @chiomadesigns · portfolio links",
             "3 years designing thumbnails for Nigerian YouTubers.", "pending")
        )

    conn.commit()
    conn.close()
    print("Database initialized.")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_token(user_id: int) -> str:
    token = secrets.token_hex(32)
    conn = get_db()
    conn.execute("INSERT INTO tokens (token, user_id) VALUES (?, ?)", (token, user_id))
    conn.commit()
    conn.close()
    return token


def get_user_from_token(token: str):
    if not token:
        return None
    conn = get_db()
    row = conn.execute(
        """SELECT u.* FROM users u
           JOIN tokens t ON t.user_id = u.id
           WHERE t.token = ?""",
        (token,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# HTTP Handler
# ─────────────────────────────────────────────

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message, status=400):
        self._json_response({"error": message}, status)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode())
        except Exception:
            return {}

    def _auth_user(self):
        auth = self.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
        return get_user_from_token(token)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # Serve uploaded files
        if path.startswith("/uploads/"):
            import os, mimetypes
            fname = path.split("/uploads/", 1)[-1]
            # prevent path traversal
            fname = os.path.basename(fname)
            fpath = os.path.join(os.path.dirname(__file__) or ".", "uploads", fname)
            if not os.path.isfile(fpath):
                return self._error("File not found", 404)
            ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", len(data))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
            return

        # Health
        if path == "/api/health":
            return self._json_response({"status": "ok", "service": "ZubbyEdit API", "time": datetime.now(timezone.utc).isoformat()})

        # Categories
        if path == "/api/categories":
            conn = get_db()
            rows = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
            conn.close()
            return self._json_response({"categories": rows_to_list(rows)})

        # Listings (public)
        if path == "/api/listings":
            conn = get_db()
            rows = conn.execute("""
                SELECT l.*, u.name as seller_name, c.name as category_name
                FROM listings l
                JOIN users u ON u.id = l.seller_id
                LEFT JOIN categories c ON c.id = l.category_id
                WHERE l.status = 'active'
                ORDER BY l.created_at DESC
            """).fetchall()
            conn.close()
            return self._json_response({"listings": rows_to_list(rows)})

        # Single listing
        m = re.match(r"^/api/listings/(\d+)$", path)
        if m:
            lid = int(m.group(1))
            conn = get_db()
            row = conn.execute("""
                SELECT l.*, u.name as seller_name, c.name as category_name
                FROM listings l
                JOIN users u ON u.id = l.seller_id
                LEFT JOIN categories c ON c.id = l.category_id
                WHERE l.id = ?
            """, (lid,)).fetchone()
            conn.close()
            if not row:
                return self._error("Listing not found", 404)
            return self._json_response({"listing": row_to_dict(row)})

        # Me
        if path == "/api/me":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)
            user.pop("password_hash", None)
            return self._json_response({"user": user})

        # My orders
        if path == "/api/orders":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)
            conn = get_db()
            rows = conn.execute("""
                SELECT * FROM orders
                WHERE buyer_id = ? OR seller_id = ?
                ORDER BY created_at DESC
            """, (user["id"], user["id"])).fetchall()
            conn.close()
            return self._json_response({"orders": rows_to_list(rows)})

        # Single order
        m = re.match(r"^/api/orders/(\d+)$", path)
        if m:
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)
            oid = int(m.group(1))
            conn = get_db()
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
            conn.close()
            if not row:
                return self._error("Order not found", 404)
            return self._json_response({"order": row_to_dict(row)})

        # Wallet
        if path == "/api/wallet":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)
            conn = get_db()
            wallet = conn.execute("SELECT * FROM wallets WHERE user_id = ?", (user["id"],)).fetchone()
            txns = conn.execute(
                "SELECT * FROM wallet_transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
                (user["id"],)
            ).fetchall()
            conn.close()
            return self._json_response({
                "wallet": row_to_dict(wallet) or {"available": 0, "pending": 0},
                "transactions": rows_to_list(txns)
            })

        # Verifications (admin / own)
        if path == "/api/verifications":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)
            conn = get_db()
            # For demo: anyone can see pending (God view)
            rows = conn.execute("""
                SELECT v.*, u.name as user_name
                FROM verifications v
                JOIN users u ON u.id = v.user_id
                ORDER BY v.created_at DESC
            """).fetchall()
            conn.close()
            return self._json_response({"verifications": rows_to_list(rows)})

        # Chat messages for a thread
        m = re.match(r"^/api/chat/(.+)$", path)
        if m:
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)
            thread_id = m.group(1)
            conn = get_db()
            rows = conn.execute(
                "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
                (thread_id,)
            ).fetchall()
            conn.close()
            return self._json_response({"messages": rows_to_list(rows)})

        self._error("Not found", 404)

    def _handle_upload(self):
        """Handle multipart file upload. Saves to uploads/ and returns path."""
        user = self._auth_user()
        # Allow unauthenticated for demo simplicity on some flows
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            return self._error("Expected multipart/form-data")

        import cgi, os, uuid
        # cgi.FieldStorage needs a file-like with headers
        length = int(self.headers.get("Content-Length", 0))
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": str(length),
        }
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=environ)

        if "file" not in form:
            return self._error("No file field")

        file_item = form["file"]
        if not file_item.filename:
            return self._error("Empty filename")

        # Sanitize + unique name
        ext = os.path.splitext(file_item.filename)[1][:10] or ".bin"
        safe_name = f"{uuid.uuid4().hex}{ext}"
        upload_dir = os.path.join(os.path.dirname(__file__) or ".", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        dest = os.path.join(upload_dir, safe_name)

        with open(dest, "wb") as f:
            f.write(file_item.file.read())

        size = os.path.getsize(dest)
        return self._json_response({
            "filename": safe_name,
            "original": file_item.filename,
            "url": f"/uploads/{safe_name}",
            "size": size
        }, 201)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/api/upload":
            return self._handle_upload()

        body = self._read_json()

        # Register
        if path == "/api/auth/register":
            name = (body.get("name") or "").strip()
            email = (body.get("email") or "").strip().lower()
            phone = (body.get("phone") or "").strip()
            password = body.get("password") or ""
            role = body.get("role") or "buyer"

            if not name or not email or not password:
                return self._error("name, email and password are required")
            if len(password) < 6:
                return self._error("Password must be at least 6 characters")
            if role not in ("buyer", "seller"):
                role = "buyer"

            conn = get_db()
            try:
                c = conn.cursor()
                c.execute(
                    "INSERT INTO users (name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                    (name, email, phone, hash_password(password), role)
                )
                user_id = c.lastrowid
                c.execute("INSERT INTO wallets (user_id, available, pending) VALUES (?, 0, 0)", (user_id,))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.close()
                return self._error("Email already registered", 409)
            conn.close()

            token = create_token(user_id)
            return self._json_response({
                "token": token,
                "user": {"id": user_id, "name": name, "email": email, "phone": phone, "role": role}
            }, 201)

        # Login
        if path == "/api/auth/login":
            email = (body.get("email") or "").strip().lower()
            password = body.get("password") or ""

            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            conn.close()

            if not user or not verify_password(password, user["password_hash"]):
                return self._error("Invalid email or password", 401)

            token = create_token(user["id"])
            u = dict(user)
            u.pop("password_hash", None)
            return self._json_response({"token": token, "user": u})

        # Create listing
        if path == "/api/listings":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            title = (body.get("title") or "").strip()
            description = (body.get("description") or "").strip()
            price = body.get("price")
            delivery = body.get("delivery") or "2 days"
            category_id = body.get("category_id")

            if not title or not price:
                return self._error("title and price are required")

            conn = get_db()
            c = conn.cursor()
            c.execute(
                """INSERT INTO listings (seller_id, category_id, title, description, price, delivery)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user["id"], category_id, title, description, int(price), delivery)
            )
            lid = c.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM listings WHERE id = ?", (lid,)).fetchone()
            conn.close()
            return self._json_response({"listing": row_to_dict(row)}, 201)

        # Create order
        if path == "/api/orders":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            listing_id = body.get("listing_id")
            brief = (body.get("brief") or "").strip()
            service_title = body.get("service_title") or "Service"
            seller_name = body.get("seller_name") or "Seller"
            price = body.get("price")
            base_price = body.get("base_price") or price
            seller_id = body.get("seller_id")

            if not price:
                return self._error("price is required")

            conn = get_db()
            c = conn.cursor()
            c.execute(
                """INSERT INTO orders
                   (buyer_id, seller_id, listing_id, service_title, seller_name, price, base_price, brief, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'in_progress')""",
                (user["id"], seller_id, listing_id, service_title, seller_name, int(price), int(base_price), brief)
            )
            oid = c.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
            conn.close()
            return self._json_response({"order": row_to_dict(row)}, 201)

        # Submit verification
        if path == "/api/verifications":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            category = (body.get("category") or "").strip()
            proof = (body.get("proof") or "").strip()
            why = (body.get("why") or "").strip()

            if not category or not proof:
                return self._error("category and proof are required")

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "INSERT INTO verifications (user_id, category, proof, why) VALUES (?, ?, ?, ?)",
                (user["id"], category, proof, why)
            )
            vid = c.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM verifications WHERE id = ?", (vid,)).fetchone()
            conn.close()
            return self._json_response({"verification": row_to_dict(row)}, 201)

        # Send chat message
        if path == "/api/chat":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            thread_id = body.get("thread_id")
            text = (body.get("text") or "").strip()
            if not thread_id or not text:
                return self._error("thread_id and text are required")

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "INSERT INTO messages (thread_id, sender_id, text) VALUES (?, ?, ?)",
                (thread_id, user["id"], text)
            )
            mid = c.lastrowid
            conn.commit()
            row = conn.execute("SELECT * FROM messages WHERE id = ?", (mid,)).fetchone()
            conn.close()
            return self._json_response({"message": row_to_dict(row)}, 201)

        # Withdraw
        if path == "/api/wallet/withdraw":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            amount = int(body.get("amount") or 0)
            bank = body.get("bank") or ""
            account = body.get("account") or ""
            name = body.get("name") or ""

            if amount <= 0:
                return self._error("Invalid amount")

            conn = get_db()
            wallet = conn.execute("SELECT * FROM wallets WHERE user_id = ?", (user["id"],)).fetchone()
            if not wallet or wallet["available"] < amount:
                conn.close()
                return self._error("Insufficient balance")

            conn.execute(
                "UPDATE wallets SET available = available - ? WHERE user_id = ?",
                (amount, user["id"])
            )
            conn.execute(
                """INSERT INTO wallet_transactions (user_id, type, title, amount, status)
                   VALUES (?, 'withdrawal', ?, ?, 'processing')""",
                (user["id"], f"Withdrawal to {bank}", -amount)
            )
            conn.commit()
            conn.close()
            return self._json_response({"success": True, "message": "Withdrawal submitted"})


        # ── Paystack: Initialize payment ──
        if path == "/api/payments/initialize":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            amount = int(body.get("amount") or 0)  # in Naira
            order_id = body.get("order_id")
            email = user.get("email") or body.get("email") or "customer@zubbyedit.com"

            if amount <= 0:
                return self._error("Invalid amount")

            # DEMO MODE: no real Paystack secret key configured.
            # In production set PAYSTACK_SECRET_KEY env var and call Paystack API.
            import os, uuid
            secret = os.environ.get("PAYSTACK_SECRET_KEY", "")

            reference = f"ZE-{uuid.uuid4().hex[:12].upper()}"

            if secret:
                # Real Paystack call
                import urllib.request
                payload = json.dumps({
                    "email": email,
                    "amount": amount * 100,  # kobo
                    "reference": reference,
                    "callback_url": body.get("callback_url") or "http://localhost:9000/?payment=success",
                    "metadata": {"order_id": order_id, "user_id": user["id"]}
                }).encode()
                req = urllib.request.Request(
                    "https://api.paystack.co/transaction/initialize",
                    data=payload,
                    headers={
                        "Authorization": f"Bearer {secret}",
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        result = json.loads(resp.read().decode())
                    return self._json_response(result)
                except Exception as e:
                    return self._error(f"Paystack error: {e}", 502)
            else:
                # Demo: return a fake authorization URL that the frontend treats as success
                return self._json_response({
                    "status": True,
                    "message": "Authorization URL created (DEMO MODE)",
                    "data": {
                        "authorization_url": f"http://localhost:9000/?payment=demo&ref={reference}&amount={amount}&order_id={order_id or ''}",
                        "access_code": "demo_access",
                        "reference": reference
                    },
                    "demo": True
                })

        # ── Paystack: Verify payment ──
        if path == "/api/payments/verify":
            user = self._auth_user()
            if not user:
                return self._error("Unauthorized", 401)

            reference = body.get("reference") or ""
            if not reference:
                return self._error("reference required")

            import os
            secret = os.environ.get("PAYSTACK_SECRET_KEY", "")

            if secret:
                import urllib.request
                req = urllib.request.Request(
                    f"https://api.paystack.co/transaction/verify/{reference}",
                    headers={"Authorization": f"Bearer {secret}"}
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        result = json.loads(resp.read().decode())
                    return self._json_response(result)
                except Exception as e:
                    return self._error(f"Verify error: {e}", 502)
            else:
                # Demo: always succeed
                return self._json_response({
                    "status": True,
                    "message": "Verification successful (DEMO MODE)",
                    "data": {
                        "status": "success",
                        "reference": reference,
                        "amount": body.get("amount", 0)
                    },
                    "demo": True
                })


        self._error("Not found", 404)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        body = self._read_json()
        user = self._auth_user()
        if not user:
            return self._error("Unauthorized", 401)

        # Update order status (deliver / accept / revision)
        m = re.match(r"^/api/orders/(\d+)$", path)
        if m:
            oid = int(m.group(1))
            status = body.get("status")
            delivery_file = body.get("delivery_file")
            delivery_note = body.get("delivery_note")

            allowed = {"in_progress", "delivered", "completed", "revision"}
            if status and status not in allowed:
                return self._error("Invalid status")

            conn = get_db()
            order = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
            if not order:
                conn.close()
                return self._error("Order not found", 404)

            updates = []
            params = []
            if status:
                updates.append("status = ?")
                params.append(status)
            if delivery_file is not None:
                updates.append("delivery_file = ?")
                params.append(delivery_file)
            if delivery_note is not None:
                updates.append("delivery_note = ?")
                params.append(delivery_note)

            if updates:
                params.append(oid)
                conn.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = ?", params)

            # If completed, credit seller wallet
            if status == "completed" and order["seller_id"]:
                base = order["base_price"] or order["price"]
                conn.execute(
                    "UPDATE wallets SET available = available + ? WHERE user_id = ?",
                    (base, order["seller_id"])
                )
                conn.execute(
                    """INSERT INTO wallet_transactions (user_id, type, title, amount, status)
                       VALUES (?, 'earning', ?, ?, 'completed')""",
                    (order["seller_id"], order["service_title"], base)
                )

            conn.commit()
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
            conn.close()
            return self._json_response({"order": row_to_dict(row)})

        # Approve / reject verification
        m = re.match(r"^/api/verifications/(\d+)$", path)
        if m:
            vid = int(m.group(1))
            status = body.get("status")  # approved | rejected
            if status not in ("approved", "rejected", "pending"):
                return self._error("Invalid status")

            conn = get_db()
            conn.execute("UPDATE verifications SET status = ? WHERE id = ?", (status, vid))
            conn.commit()
            row = conn.execute("SELECT * FROM verifications WHERE id = ?", (vid,)).fetchone()
            conn.close()
            if not row:
                return self._error("Not found", 404)
            return self._json_response({"verification": row_to_dict(row)})

        self._error("Not found", 404)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    server = HTTPServer(("0.0.0.0", PORT), APIHandler)
    print(f"ZubbyEdit API running on http://0.0.0.0:{PORT}")
    print("Endpoints: /api/health  /api/auth/register  /api/auth/login  /api/listings  /api/orders ...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()
