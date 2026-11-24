"""Shared Siloti stock manager web server (Python standard library only)."""
import json
import mimetypes
import sqlite3
import uuid
import hashlib
import hmac
import html
import re
import os
import secrets
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
import webbrowser

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("DB_PATH", str(ROOT / "siloti_stock.sqlite3"))).resolve()
PRODUCT_SKUS = {"Red Chilli": ["100g", "200g"], "Coriander": ["100g", "200g"], "Black Pepper": ["100g"], "Turmeric": ["100g", "200g"]}
SKU_MRPS = {
    "Red Chilli": {"100g": 67.00, "200g": 132.00},
    "Coriander": {"100g": 46.00, "200g": 90.00},
    "Black Pepper": {"100g": 182.00},
    "Turmeric": {"100g": 48.00, "200g": 95.00},
}
DEFAULT_OPENING = 21
SESSION_DAYS = 14
PASSWORD_ITERATIONS = 310_000


def connect():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


@contextmanager
def database():
    db = connect()
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.execute("CREATE TABLE IF NOT EXISTS opening (product TEXT, sku TEXT, quantity INTEGER NOT NULL, PRIMARY KEY(product,sku))")
        db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS admin_recovery (user_id INTEGER PRIMARY KEY REFERENCES users(id), code_hash TEXT NOT NULL, requested_at TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT NOT NULL, attempted_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS expenses (id TEXT PRIMARY KEY, date TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', amount REAL NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS bills (id TEXT PRIMARY KEY, date TEXT NOT NULL, customer TEXT NOT NULL DEFAULT '', total REAL NOT NULL, html TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS movements (
            id TEXT PRIMARY KEY, date TEXT NOT NULL, product TEXT NOT NULL, sku TEXT NOT NULL,
            type TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price REAL, sale_amount REAL,
            party TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '')""")
        migrate_black_pepper_sku(db)
        for product, skus in PRODUCT_SKUS.items():
            for sku in skus:
                db.execute("INSERT OR IGNORE INTO opening VALUES (?,?,?)", (product, sku, DEFAULT_OPENING))
        # One-time import preserves the existing desktop tool's stock history.
        if db.execute("SELECT 1 FROM settings WHERE key='legacy_imported'").fetchone() is None:
            source = ROOT / "siloti_stock_data.json"
            if source.exists():
                try:
                    data = json.loads(source.read_text(encoding="utf-8"))
                    for key, qty in data.get("opening", {}).items():
                        if "|" in key:
                            product, sku = key.split("|", 1)
                            if product == "Black Pepper" and sku == "50g": sku = "100g"
                            if product in PRODUCT_SKUS and sku in PRODUCT_SKUS[product]:
                                db.execute("UPDATE opening SET quantity=? WHERE product=? AND sku=?", (int(qty), product, sku))
                    for r in data.get("movements", []):
                        if r.get("product") == "Black Pepper" and r.get("sku") == "50g": r["sku"] = "100g"
                        if r.get("product") in PRODUCT_SKUS and r.get("sku") in PRODUCT_SKUS[r["product"]] and r.get("type") in ("IN", "OUT"):
                            db.execute("INSERT OR IGNORE INTO movements VALUES (?,?,?,?,?,?,?,?,?,?)", (
                                str(r.get("id") or uuid.uuid4().hex), r.get("date", date.today().isoformat()), r["product"], r["sku"], r["type"], int(r.get("quantity", 0)), r.get("unit_price"), r.get("sale_amount"), r.get("party", ""), r.get("reference", "")))
                except (ValueError, OSError, TypeError):
                    pass
            db.execute("INSERT INTO settings VALUES ('legacy_imported','yes')")
        if db.execute("SELECT 1 FROM settings WHERE key='expenses_imported'").fetchone() is None:
            source=ROOT/"siloti_expense_data.json"
            if source.exists():
                try:
                    for r in json.loads(source.read_text(encoding="utf-8")).get("expenses",[]):
                        db.execute("INSERT OR IGNORE INTO expenses VALUES (?,?,?,?,?)",(str(r.get("id") or uuid.uuid4().hex),r.get("date",date.today().isoformat()),r.get("category","Other"),r.get("description",""),float(r.get("amount",0))))
                except (ValueError,OSError,TypeError):pass
            db.execute("INSERT INTO settings VALUES ('expenses_imported','yes')")
        migrate_catalog_prices(db)


def migrate_black_pepper_sku(db):
    if db.execute("SELECT 1 FROM settings WHERE key='black_pepper_100g_v1'").fetchone():
        return
    old = db.execute("SELECT quantity FROM opening WHERE product='Black Pepper' AND sku='50g'").fetchone()
    if old:
        existing = db.execute("SELECT quantity FROM opening WHERE product='Black Pepper' AND sku='100g'").fetchone()
        if existing:
            db.execute("UPDATE opening SET quantity=? WHERE product='Black Pepper' AND sku='100g'", (old['quantity'],))
            db.execute("DELETE FROM opening WHERE product='Black Pepper' AND sku='50g'")
        else:
            db.execute("UPDATE opening SET sku='100g' WHERE product='Black Pepper' AND sku='50g'")
    db.execute("UPDATE movements SET sku='100g' WHERE product='Black Pepper' AND sku='50g'")
    db.execute("INSERT INTO settings VALUES ('black_pepper_100g_v1','yes')")


class BillTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows=[]
        self.row=None
        self.cell=None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row=[]
        elif tag == 'td' and self.row is not None: self.cell=''

    def handle_data(self, data):
        if self.cell is not None: self.cell += data

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(self.cell.strip()); self.cell=None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row); self.row=None


def reprice_bill_html(content):
    parser=BillTableParser();parser.feed(content)
    items=[]
    for cells in parser.rows:
        if len(cells)<7 or cells[0].strip().lower()=='total': continue
        product=html.unescape(cells[0]);sku=cells[2].strip().lower()
        if product=='Black Pepper' and sku=='50g': sku='100g'
        if product not in SKU_MRPS or sku not in SKU_MRPS[product]: continue
        quantity=int(re.sub(r'[^0-9]','',cells[1]) or '0')
        discount=float(re.sub(r'[^0-9.]','',cells[4]) or '0')
        mrp=SKU_MRPS[product][sku];final=round(mrp*(1-discount/100),2);amount=round(quantity*final,2)
        items.append({'product':product,'sku':sku,'quantity':quantity,'discount_pct':discount,'mrp':mrp,'final_price':final,'amount':amount})
    if not items: return content, [], None
    total=round(sum(i['amount'] for i in items),2)
    rows=''.join(f"<tr><td>{html.escape(i['product'])}</td><td class='n'>{i['quantity']}</td><td>{html.escape(i['sku'])}</td><td class='n'>₹{i['mrp']:,.2f}</td><td class='n'>{i['discount_pct']:g}%</td><td class='n'>₹{i['final_price']:,.2f}</td><td class='n'>₹{i['amount']:,.2f}</td></tr>" for i in items)
    rows+=f"<tr class='total'><td colspan='6'>Total</td><td class='n'>₹{total:,.2f}</td></tr>"
    updated,count=re.subn(r'<tbody>.*?</tbody>',f'<tbody>{rows}</tbody>',content,count=1,flags=re.S|re.I)
    return updated,items,total if count else None


def migrate_catalog_prices(db):
    if db.execute("SELECT 1 FROM settings WHERE key='sku_mrp_prices_v1'").fetchone():
        return
    bill_items={}
    for bill in db.execute("SELECT id,date,customer,html FROM bills").fetchall():
        updated,items,total=reprice_bill_html(bill['html'])
        if items:
            db.execute("UPDATE bills SET html=?,total=? WHERE id=?",(updated,total,bill['id']))
            bill_items[bill['id']]=items
    bills_dir=ROOT/'bills'
    if bills_dir.exists():
        for path in bills_dir.glob('*.html'):
            content=path.read_text(encoding='utf-8')
            updated,items,_=reprice_bill_html(content)
            if items:
                path.write_text(updated,encoding='utf-8')
                bill_id=path.stem
                bill_items[bill_id]=items
    billed_rows={}
    for bill_id,items in bill_items.items():
        for item in items:
            billed_rows.setdefault((bill_id,item['product'],item['sku']),[]).append(item)
    out_rows=db.execute("SELECT rowid,id,product,sku,quantity,reference FROM movements WHERE type='OUT'").fetchall()
    for row in out_rows:
        product,sku=row['product'],row['sku']
        if product=='Black Pepper' and sku=='50g': sku='100g'
        price=SKU_MRPS.get(product,{}).get(sku)
        if price is None: continue
        sale_price=price
        reference=row['reference'] or ''
        if reference.startswith('Bill '):
            bill_id=reference[5:]
            candidates=billed_rows.get((bill_id,product,sku),[])
            matched=next((item for item in candidates if item['quantity']==row['quantity']),None)
            if matched:
                sale_price=matched['final_price'];candidates.remove(matched)
        db.execute("UPDATE movements SET sku=?,unit_price=?,sale_amount=? WHERE rowid=?",(sku,sale_price,row['quantity']*sale_price,row['rowid']))
    db.execute("UPDATE movements SET sku='100g' WHERE product='Black Pepper' AND sku='50g'")
    db.execute("INSERT INTO settings VALUES ('sku_mrp_prices_v1','yes')")


def snapshot():
    with database() as db:
        openings = {(r["product"], r["sku"]): r["quantity"] for r in db.execute("SELECT * FROM opening")}
        movements = [dict(r) for r in db.execute("SELECT * FROM movements ORDER BY date DESC, rowid DESC")]
    balances = []
    for product, skus in PRODUCT_SKUS.items():
        for sku in skus:
            rows = [m for m in movements if m["product"] == product and m["sku"] == sku]
            ins = sum(m["quantity"] for m in rows if m["type"] == "IN")
            outs = sum(m["quantity"] for m in rows if m["type"] == "OUT")
            sales = sum((m["sale_amount"] if m["sale_amount"] is not None else m["quantity"] * (m["unit_price"] if m["unit_price"] is not None else SKU_MRPS[product][sku])) for m in rows if m["type"] == "OUT")
            balances.append({"product": product, "sku": sku, "opening": openings.get((product, sku), DEFAULT_OPENING), "in": ins, "out": outs, "current": openings.get((product, sku), DEFAULT_OPENING) + ins - outs, "sales": sales})
    return {"products": PRODUCT_SKUS, "mrps": SKU_MRPS, "balances": balances, "movements": movements}


def default_sell_price(product, sku):
    return SKU_MRPS[product][sku]


def password_digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PASSWORD_ITERATIONS).hex()


def valid_username(value):
    return isinstance(value, str) and 3 <= len(value) <= 40 and value.replace("_", "").replace("-", "").isalnum()


def new_session(db, user_id):
    token = secrets.token_urlsafe(36)
    csrf = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, expires))
    return token, csrf


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY"); self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(raw)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")

    def session(self):
        cookie = self.headers.get("Cookie", "")
        token = next((part.strip()[7:] for part in cookie.split(";") if part.strip().startswith("siloti=") ), "")
        if not token: return None
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with database() as db:
            row = db.execute("SELECT s.csrf,s.expires_at,u.id,u.username,u.role,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash,)).fetchone()
            if not row or not row["active"] or row["expires_at"] < datetime.now(timezone.utc).isoformat():
                db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,)); return None
            return {"id": row["id"], "username": row["username"], "role": row["role"], "csrf": row["csrf"], "token_hash": token_hash}

    def require_user(self, admin=False, csrf=True):
        user = self.session()
        if not user:
            self.reply(401, {"error": "Please sign in again."}); return None
        if admin and user["role"] != "admin":
            self.reply(403, {"error": "Administrator access required."}); return None
        if csrf and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), user["csrf"]):
            self.reply(403, {"error": "Please refresh the page and try again."}); return None
        return user

    def set_session_cookie(self, token):
        secure = "; Secure" if os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true", "yes") else ""
        self.send_header("Set-Cookie", f"siloti={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_DAYS*86400}{secure}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/auth/status":
            with database() as db: user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            user = self.session()
            return self.reply(200, {"setup_required": user_count == 0, "user": {k:user[k] for k in ("username", "role")} if user else None, "csrf": user["csrf"] if user else None})
        if path == "/api/users":
            user = self.require_user(admin=True, csrf=False)
            if not user: return
            with database() as db:
                users = [dict(r) for r in db.execute("SELECT id,username,role,active,created_at FROM users ORDER BY id")]
            return self.reply(200, {"users": users})
        if path == "/api/data":
            if not self.require_user(csrf=False): return
            return self.reply(200, snapshot())
        if path == "/api/expenses":
            if not self.require_user(csrf=False): return
            with database() as db: rows=[dict(r) for r in db.execute("SELECT * FROM expenses ORDER BY date DESC,rowid DESC")]
            return self.reply(200,{"expenses":rows})
        if path.startswith("/bill/"):
            if not self.require_user(csrf=False): return
            with database() as db: row=db.execute("SELECT html FROM bills WHERE id=?",(path[6:],)).fetchone()
            if not row:self.send_error(404);return
            raw=row["html"].encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(raw)));self.send_header("X-Content-Type-Options","nosniff");self.send_header("X-Frame-Options","DENY");self.send_header("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(raw);return
        if path == "/":
            path = "/index.html"
        target = (ROOT / "web" / path.lstrip("/")).resolve()
        if not target.is_relative_to((ROOT / "web").resolve()) or not target.is_file():
            self.send_error(404); return
        raw = target.read_bytes(); self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-cache"); self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(raw)

    def do_POST(self):
        try:
            data = self.body(); path = urlparse(self.path).path
            if path == "/api/auth/recovery/request":
                username=str(data.get("username", "")).strip()
                code=None
                now=datetime.now(timezone.utc)
                with database() as db:
                    db.execute("BEGIN IMMEDIATE")
                    admin=db.execute("SELECT id,username FROM users WHERE username=? COLLATE NOCASE AND role='admin' AND active=1",(username,)).fetchone()
                    if admin:
                        pending=db.execute("SELECT expires_at FROM admin_recovery WHERE user_id=?",(admin["id"],)).fetchone()
                        if not pending or pending["expires_at"]<=now.isoformat():
                            code=secrets.token_urlsafe(9)
                            db.execute("INSERT INTO admin_recovery(user_id,code_hash,requested_at,expires_at,attempts) VALUES (?,?,?,?,0) ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash,requested_at=excluded.requested_at,expires_at=excluded.expires_at,attempts=0",(admin["id"],hashlib.sha256(code.encode()).hexdigest(),now.isoformat(),(now+timedelta(minutes=10)).isoformat()))
                if code:
                    print(f"[ADMIN PASSWORD RECOVERY] username={username} code={code} expires_in=10_minutes",flush=True)
                return self.reply(200,{"message":"If this admin account can be recovered, a one-time code has been written to the app server log. It expires in 10 minutes."})
            if path == "/api/auth/recovery/complete":
                username=str(data.get("username", "")).strip();code=data.get("code", "");password=data.get("password", "")
                if not isinstance(code,str) or not isinstance(password,str) or len(password)<12:
                    return self.reply(400,{"error":"Enter the recovery code and a new password with at least 12 characters."})
                now=datetime.now(timezone.utc);session=None;invalid=False
                with database() as db:
                    db.execute("BEGIN IMMEDIATE")
                    admin=db.execute("SELECT id,username FROM users WHERE username=? COLLATE NOCASE AND role='admin' AND active=1",(username,)).fetchone()
                    recovery=db.execute("SELECT * FROM admin_recovery WHERE user_id=?",(admin["id"],)).fetchone() if admin else None
                    if not recovery or recovery["expires_at"]<=now.isoformat() or recovery["attempts"]>=5:
                        if recovery:db.execute("DELETE FROM admin_recovery WHERE user_id=?",(admin["id"],))
                        invalid=True
                    elif not hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(),recovery["code_hash"]):
                        attempts=recovery["attempts"]+1
                        if attempts>=5:db.execute("DELETE FROM admin_recovery WHERE user_id=?",(admin["id"],))
                        else:db.execute("UPDATE admin_recovery SET attempts=? WHERE user_id=?",(attempts,admin["id"]))
                        invalid=True
                    else:
                        salt=secrets.token_bytes(16).hex()
                        db.execute("UPDATE users SET password_hash=?,salt=? WHERE id=?",(password_digest(password,salt),salt,admin["id"]))
                        db.execute("DELETE FROM sessions WHERE user_id=?",(admin["id"],))
                        db.execute("DELETE FROM admin_recovery WHERE user_id=?",(admin["id"],))
                        session=new_session(db,admin["id"])
                if invalid:return self.reply(400,{"error":"The recovery code is invalid or expired. Request a new code from this page."})
                token,csrf=session
                raw=json.dumps({"user":{"username":username,"role":"admin"},"csrf":csrf}).encode()
                self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store");self.set_session_cookie(token);self.end_headers();self.wfile.write(raw);return
            if path == "/api/auth/setup":
                username, password = str(data.get("username", "")).strip(), data.get("password", "")
                if not valid_username(username) or not isinstance(password, str) or len(password) < 12:
                    return self.reply(400, {"error": "Use a 3–40 character username and a password with at least 12 characters."})
                salt = secrets.token_bytes(16).hex()
                with database() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]: return self.reply(409, {"error": "Admin setup has already been completed. Sign in instead."})
                    cur = db.execute("INSERT INTO users(username,password_hash,salt,role,created_at) VALUES (?,?,?,'admin',?)", (username, password_digest(password,salt),salt,datetime.now(timezone.utc).isoformat()))
                    token, csrf = new_session(db, cur.lastrowid)
                raw = json.dumps({"user":{"username":username,"role":"admin"},"csrf":csrf}).encode()
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.set_session_cookie(token); self.end_headers(); self.wfile.write(raw); return
            if path == "/api/auth/login":
                username, password = str(data.get("username", "")).strip(), data.get("password", "")
                if not isinstance(password,str):password=""
                forwarded=self.headers.get("X-Forwarded-For", "").split(",",1)[0].strip()
                ip=forwarded if os.environ.get("TRUST_PROXY", "") == "1" and forwarded else self.client_address[0]
                with database() as db:
                    db.execute("BEGIN IMMEDIATE")
                    cutoff=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
                    db.execute("DELETE FROM login_attempts WHERE attempted_at<?",(cutoff,))
                    if db.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=?",(ip,)).fetchone()[0]>=10:
                        return self.reply(429,{"error":"Too many sign-in attempts. Wait 15 minutes and try again."})
                    row = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND active=1", (username,)).fetchone()
                    if not row or not hmac.compare_digest(password_digest(password,row["salt"]),row["password_hash"]):
                        db.execute("INSERT INTO login_attempts VALUES (?,?)",(ip,datetime.now(timezone.utc).isoformat()))
                        return self.reply(401,{"error":"Username or password is incorrect."})
                    db.execute("DELETE FROM login_attempts WHERE ip=?",(ip,))
                    token, csrf = new_session(db,row["id"])
                raw=json.dumps({"user":{"username":row["username"],"role":row["role"]},"csrf":csrf}).encode()
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Content-Length",str(len(raw))); self.set_session_cookie(token); self.end_headers(); self.wfile.write(raw); return
            if path == "/api/auth/logout":
                user=self.require_user()
                if not user:return
                with database() as db: db.execute("DELETE FROM sessions WHERE token_hash=?",(user["token_hash"],))
                self.send_response(200); self.send_header("Set-Cookie","siloti=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(b'{"ok":true}'); return
            if path == "/api/users":
                if not self.require_user(admin=True): return
                username,password=str(data.get("username", "")).strip(),data.get("password", "")
                if not valid_username(username) or not isinstance(password,str) or len(password)<12:
                    return self.reply(400,{"error":"Use a 3–40 character username and a password with at least 12 characters."})
                salt=secrets.token_bytes(16).hex()
                with database() as db: db.execute("INSERT INTO users(username,password_hash,salt,role,created_at) VALUES (?,?,?,'user',?)",(username,password_digest(password,salt),salt,datetime.now(timezone.utc).isoformat()))
                return self.reply(200,{"ok":True})
            if path == "/api/users/active":
                current=self.require_user(admin=True)
                if not current:return
                uid=int(data["id"]); active=1 if data["active"] else 0
                if uid==current["id"]:return self.reply(400,{"error":"You cannot disable your own admin account."})
                with database() as db:
                    db.execute("UPDATE users SET active=? WHERE id=? AND role!='admin'",(active,uid))
                    if not active:db.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
                return self.reply(200,{"ok":True})
            if path == "/api/users/password":
                current=self.require_user(admin=True)
                if not current:return
                uid=int(data["id"]);password=data.get("password", "")
                if not isinstance(password,str) or len(password)<12:return self.reply(400,{"error":"Use a password with at least 12 characters."})
                salt=secrets.token_bytes(16).hex()
                with database() as db:
                    changed=db.execute("UPDATE users SET password_hash=?,salt=? WHERE id=? AND role!='admin'",(password_digest(password,salt),salt,uid)).rowcount
                    if changed:db.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
                if not changed:return self.reply(404,{"error":"User not found."})
                return self.reply(200,{"ok":True})
            user = self.require_user()
            if not user: return
            if path in ("/api/expenses","/api/expenses/delete"):
                if path.endswith("/delete"):
                    db_call="DELETE FROM expenses WHERE id=?";params=[(str(i),) for i in data.get("ids",[])]
                    with database() as db:db.executemany(db_call,params)
                else:
                    expense_date=date.fromisoformat(data["date"]).isoformat();category=str(data.get("category",""));amount=float(data["amount"]);description=str(data.get("description","")).strip()
                    categories=["Stock Purchase","Packaging","Shipping","Travel","Salary / Labour","Utilities","Marketing","Rent","Other"]
                    if category not in categories or amount<=0:return self.reply(400,{"error":"Choose a category and enter an amount greater than zero."})
                    with database() as db:db.execute("INSERT INTO expenses VALUES (?,?,?,?,?)",(uuid.uuid4().hex,expense_date,category,description,amount))
                with database() as db:rows=[dict(r) for r in db.execute("SELECT * FROM expenses ORDER BY date DESC,rowid DESC")]
                return self.reply(200,{"expenses":rows})
            if path == "/api/expenses/update":
                expense_date=date.fromisoformat(data["date"]).isoformat();category=str(data.get("category",""));amount=float(data["amount"]);description=str(data.get("description","")).strip()
                categories=["Stock Purchase","Packaging","Shipping","Travel","Salary / Labour","Utilities","Marketing","Rent","Other"]
                if category not in categories or amount<=0:return self.reply(400,{"error":"Choose a category and enter an amount greater than zero."})
                with database() as db:changed=db.execute("UPDATE expenses SET date=?,category=?,description=?,amount=? WHERE id=?",(expense_date,category,description,amount,str(data["id"]))).rowcount
                if not changed:return self.reply(404,{"error":"Expense entry not found."})
                with database() as db:rows=[dict(r) for r in db.execute("SELECT * FROM expenses ORDER BY date DESC,rowid DESC")]
                return self.reply(200,{"expenses":rows})
            if path == "/api/bills":
                return self.create_bill(data)
            if path == "/api/movements/bulk":
                day=date.fromisoformat(data["date"]).isoformat();entries=[]
                for row in data.get("entries",[]):
                    product,sku,kind=row["product"],row["sku"],row["type"];qty=int(row["quantity"])
                    if product not in PRODUCT_SKUS or sku not in PRODUCT_SKUS[product] or kind not in ("IN","OUT") or qty<=0:raise ValueError()
                    price=(float(str(row.get("unit_price","")).replace(",","")) if str(row.get("unit_price","")).strip() else default_sell_price(product,sku)) if kind=="OUT" else None
                    if price is not None and price<0:raise ValueError()
                    entries.append((uuid.uuid4().hex,day,product,sku,kind,qty,price,qty*price if price is not None else None,str(row.get("party","")).strip(),str(row.get("reference","")).strip()))
                if not entries:return self.reply(400,{"error":"Enter at least one movement."})
                with database() as db:db.executemany("INSERT INTO movements VALUES (?,?,?,?,?,?,?,?,?,?)",entries)
                return self.reply(200,snapshot())
            if path == "/api/movements/update":
                product,sku,kind=data["product"],data["sku"],data["type"];day=date.fromisoformat(data["date"]).isoformat();qty=int(data["quantity"])
                if product not in PRODUCT_SKUS or sku not in PRODUCT_SKUS[product] or kind not in ("IN","OUT") or qty<=0:raise ValueError()
                price=(float(str(data.get("unit_price","")).replace(",","")) if str(data.get("unit_price","")).strip() else default_sell_price(product,sku)) if kind=="OUT" else None
                if price is not None and price<0:raise ValueError()
                with database() as db:changed=db.execute("UPDATE movements SET date=?,product=?,sku=?,type=?,quantity=?,unit_price=?,sale_amount=?,party=?,reference=? WHERE id=?",(day,product,sku,kind,qty,price,qty*price if price is not None else None,str(data.get("party","")).strip(),str(data.get("reference","")).strip(),str(data["id"]))).rowcount
                if not changed:return self.reply(404,{"error":"Movement entry not found."})
                return self.reply(200,snapshot())
            with database() as db:
                if path == "/api/movements":
                    product, sku, kind = data["product"], data["sku"], data["type"]
                    day = date.fromisoformat(data["date"]).isoformat()
                    qty = int(data["quantity"])
                    if product not in PRODUCT_SKUS or sku not in PRODUCT_SKUS[product] or kind not in ("IN", "OUT") or qty <= 0:
                        return self.reply(400, {"error": "Choose a valid product, SKU, movement, and positive quantity."})
                    price = (float(str(data.get("unit_price", "")).replace(",", "")) if str(data.get("unit_price", "")).strip() else default_sell_price(product,sku)) if kind == "OUT" else None
                    if price is not None and price < 0: return self.reply(400, {"error": "Price cannot be negative."})
                    db.execute("INSERT INTO movements VALUES (?,?,?,?,?,?,?,?,?,?)", (uuid.uuid4().hex, day, product, sku, kind, qty, price, qty * price if price is not None else None, str(data.get("party", "")).strip(), str(data.get("reference", "")).strip()))
                elif path == "/api/opening":
                    qty = int(data["quantity"]); product, sku = data["product"], data["sku"]
                    if qty < 0 or product not in PRODUCT_SKUS or sku not in PRODUCT_SKUS[product]: raise ValueError()
                    db.execute("UPDATE opening SET quantity=? WHERE product=? AND sku=?", (qty, product, sku))
                elif path == "/api/delete":
                    ids = data.get("ids", [])
                    db.executemany("DELETE FROM movements WHERE id=?", [(str(i),) for i in ids])
                else: return self.reply(404, {"error": "Not found"})
            self.reply(200, snapshot())
        except (ValueError, KeyError, TypeError):
            self.reply(400, {"error": "Please check the entry and try again."})
        except sqlite3.IntegrityError:
            self.reply(409,{"error":"That username is already in use."})

    def create_bill(self,data):
        import html as html_lib
        bill_date=date.fromisoformat(data["date"]).isoformat();customer=str(data.get("customer","")).strip();items=data.get("items",[])
        if not items:return self.reply(400,{"error":"Add at least one item to the bill."})
        clean=[];requested={}
        for item in items:
            product,sku=item["product"],item["sku"];qty=int(item["quantity"]);mrp=round(float(item["mrp"]),2);discount=round(float(item["discount_pct"]),2)
            if product not in PRODUCT_SKUS or sku not in PRODUCT_SKUS[product] or qty<=0 or mrp<0 or not 0<=discount<=100:raise ValueError()
            final=round(mrp*(1-discount/100),2);amount=round(qty*final,2)
            clean.append({"product":product,"sku":sku,"quantity":qty,"mrp":mrp,"discount_pct":discount,"final_price":final,"amount":amount});requested[(product,sku)]=requested.get((product,sku),0)+qty
        total=round(sum(item["amount"] for item in clean),2);bill_id="SILOTI-"+datetime.now().strftime("%Y%m%d-%H%M%S-")+uuid.uuid4().hex[:8].upper()
        rows="".join(f"<tr><td>{html_lib.escape(i['product'])}</td><td class='n'>{i['quantity']}</td><td>{html_lib.escape(i['sku'])}</td><td class='n'>₹{i['mrp']:,.2f}</td><td class='n'>{i['discount_pct']:g}%</td><td class='n'>₹{i['final_price']:,.2f}</td><td class='n'>₹{i['amount']:,.2f}</td></tr>" for i in clean)
        bill=f"<!doctype html><html><head><meta charset='utf-8'><title>Siloti Bill {bill_id}</title><style>body{{font-family:Arial,sans-serif;color:#1c2d3e;margin:32px}}h1{{color:#15334d}}.meta{{margin-bottom:22px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #d9e0e6;text-align:left}}th{{background:#edf2f6}}.n{{text-align:right}}.total td{{font-weight:bold;font-size:18px;border-top:2px solid #263d54}}@media print{{button{{display:none}}body{{margin:10mm}}}}</style></head><body><button onclick='window.print()'>Print bill</button><h1>Siloti Bill</h1><div class='meta'><b>Bill:</b> {bill_id}<br><b>Date:</b> {bill_date}<br><b>Customer:</b> {html_lib.escape(customer or 'Walk-in')}</div><table><thead><tr><th>Product</th><th>Quantity</th><th>SKU / Size</th><th>MRP / packet</th><th>Discount</th><th>Final / packet</th><th>Line total</th></tr></thead><tbody>{rows}<tr class='total'><td colspan='6'>Total</td><td class='n'>₹{total:,.2f}</td></tr></tbody></table></body></html>"
        with database() as db:
            db.execute("BEGIN IMMEDIATE")
            for (product,sku),qty in requested.items():
                opening=db.execute("SELECT quantity FROM opening WHERE product=? AND sku=?",(product,sku)).fetchone()[0]
                movements=db.execute("SELECT type,quantity FROM movements WHERE product=? AND sku=?",(product,sku)).fetchall()
                available=opening+sum(r["quantity"] if r["type"]=="IN" else -r["quantity"] for r in movements)
                if qty>available:return self.reply(409,{"error":f"{product} {sku}: {available} packet(s) available; {qty} requested."})
            db.execute("INSERT INTO bills VALUES (?,?,?,?,?)",(bill_id,bill_date,customer,total,bill))
            for item in clean:db.execute("INSERT INTO movements VALUES (?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,bill_date,item["product"],item["sku"],"OUT",item["quantity"],item["final_price"],item["amount"],customer,"Bill "+bill_id))
        return self.reply(200,{"bill_id":bill_id,"url":"/bill/"+bill_id})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    init_db()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Siloti Stock Manager is ready at http://localhost:{port}")
    if os.environ.get("OPEN_BROWSER", "1") != "0": webbrowser.open(f"http://localhost:{port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
