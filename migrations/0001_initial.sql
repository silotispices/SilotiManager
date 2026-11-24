CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS opening (product TEXT NOT NULL, sku TEXT NOT NULL, quantity INTEGER NOT NULL, PRIMARY KEY(product, sku));
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE COLLATE NOCASE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user', active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_recovery (user_id INTEGER PRIMARY KEY REFERENCES users(id), code_hash TEXT NOT NULL, requested_at TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT NOT NULL, attempted_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expenses (id TEXT PRIMARY KEY, date TEXT NOT NULL, category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', amount REAL NOT NULL);
CREATE TABLE IF NOT EXISTS bills (id TEXT PRIMARY KEY, date TEXT NOT NULL, customer TEXT NOT NULL DEFAULT '', total REAL NOT NULL, html TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS movements (id TEXT PRIMARY KEY, date TEXT NOT NULL, product TEXT NOT NULL, sku TEXT NOT NULL, type TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price REAL, sale_amount REAL, party TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS movements_date_idx ON movements(date DESC);
CREATE INDEX IF NOT EXISTS expenses_date_idx ON expenses(date DESC);
INSERT OR IGNORE INTO opening (product, sku, quantity) VALUES
  ('Red Chilli', '100g', 21), ('Red Chilli', '200g', 21),
  ('Coriander', '100g', 21), ('Coriander', '200g', 21),
  ('Black Pepper', '100g', 21), ('Turmeric', '100g', 21), ('Turmeric', '200g', 21);
