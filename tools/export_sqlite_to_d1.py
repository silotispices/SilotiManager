"""Export Siloti business records for import into the Cloudflare D1 database."""
import argparse
import sqlite3
from pathlib import Path


TABLES = {
    "settings": ("key", "value"),
    "opening": ("product", "sku", "quantity"),
    "users": ("id", "username", "password_hash", "salt", "role", "active", "created_at"),
    "expenses": ("id", "date", "category", "description", "amount"),
    "bills": ("id", "date", "customer", "total", "html"),
    "movements": ("id", "date", "product", "sku", "type", "quantity", "unit_price", "sale_amount", "party", "reference"),
}


def sql_value(value):
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="Path to siloti_stock.sqlite3")
    parser.add_argument("output", type=Path, help="Output SQL file; keep it private because it contains password hashes")
    args = parser.parse_args()

    db = sqlite3.connect(args.database)
    lines = ["-- Generated from the local Siloti SQLite database.", "-- Contains password hashes and private business records.", "BEGIN TRANSACTION;"]
    for table, columns in TABLES.items():
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            continue
        names = ", ".join('"' + name + '"' for name in columns)
        for row in db.execute(f'SELECT {names} FROM "{table}"'):
            values = ", ".join(sql_value(value) for value in row)
            lines.append(f'INSERT OR REPLACE INTO "{table}" ({names}) VALUES ({values});')
    lines.append("COMMIT;")
    db.close()
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote D1 import SQL to {args.output}. Keep this file private and delete it after the import.")


if __name__ == "__main__":
    main()
