import csv
import json
import os
import sys
import tkinter as tk
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk


PRODUCT_SKUS = {
    "Red Chilli": ["100g", "200g"],
    "Coriander": ["100g", "200g"],
    "Black Pepper": ["50g"],
    "Turmeric": ["100g", "200g"],
}
DEFAULT_OPENING = 21
DEFAULT_SELL_PRICE = 100


def stock_out_value(row):
    if row.get("type") != "OUT":
        return 0.0
    saved = row.get("sale_amount")
    if saved is not None:
        return float(saved)
    unit_price = row.get("unit_price")
    if unit_price is None:
        unit_price = DEFAULT_SELL_PRICE
    return int(row.get("quantity", 0)) * float(unit_price)
FIELDS = ["date", "product", "sku", "type", "quantity", "unit_price", "sale_amount", "party", "reference"]


def app_directory():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DATA_FILE = os.path.join(app_directory(), "siloti_stock_data.json")


class StockTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Siloti Stock Manager")
        self.geometry("1400x900")
        self.minsize(1100, 700)
        self.state("zoomed")
        self.configure(bg="#f3f6f8")
        self.data = self.load_data()
        self._style()
        self._build_ui()
        self.refresh()

    def load_data(self):
        data = {"opening": {}, "movements": []}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data.update(loaded)
            except (OSError, json.JSONDecodeError):
                messagebox.showwarning("Data file", "The saved data file could not be read. A new one will be created.")
        for product, skus in PRODUCT_SKUS.items():
            for sku in skus:
                data["opening"].setdefault(self.key(product, sku), DEFAULT_OPENING)
        data.setdefault("movements", [])
        return data

    @staticmethod
    def key(product, sku):
        return f"{product}|{sku}"

    def save_data(self):
        temp = DATA_FILE + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(temp, DATA_FILE)
        self.save_status.configure(text=f"Saved locally · {datetime.now().strftime('%H:%M')}")

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f6f8")
        style.configure("Card.TFrame", background="white")
        style.configure("TLabel", background="#f3f6f8", foreground="#223247", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground="#14283f")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#667789")
        style.configure("CardTitle.TLabel", background="white", font=("Segoe UI", 10, "bold"), foreground="#263d54")
        style.configure("Metric.TLabel", background="white", font=("Segoe UI", 18, "bold"), foreground="#15334d")
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#e8eef3", foreground="#31485d")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8), background="#176b57", foreground="white")
        style.map("Accent.TButton", background=[("active", "#125744")])
        style.configure("TButton", font=("Segoe UI", 9), padding=(9, 6))

    def _build_ui(self):
        outer = ttk.Frame(self, padding=(14, 12, 14, 10))
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 9))
        header = ttk.Frame(top)
        header.pack(side="left", fill="both", expand=True)
        ttk.Label(header, text="Siloti Stock Manager", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="Record stock movements by product and SKU. Stock balances update automatically.", style="Sub.TLabel").pack(anchor="w", pady=(3, 0))

        product_card = ttk.Frame(top, style="Card.TFrame", padding=(10, 7))
        product_card.pack(side="right", anchor="ne", padx=(12, 0))
        ttk.Label(product_card, text="Product stock overview", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 5))
        product_buttons = ttk.Frame(product_card, style="Card.TFrame")
        product_buttons.pack(anchor="e")
        ttk.Button(product_buttons, text="Current total stock", command=self.show_all_stock, padding=(7, 4)).pack(side="left", padx=(0, 5))
        for product in PRODUCT_SKUS:
            ttk.Button(product_buttons, text=product, command=lambda name=product: self.show_product(name), padding=(7, 4)).pack(side="left", padx=(0, 5))

        metrics = ttk.Frame(outer)
        metrics.pack(fill="x", pady=(0, 9))
        self.metric_labels = []
        for title in ("Packets remaining", "Stock out / sold", "Stock received", "Total sales (₹)"):
            card = ttk.Frame(metrics, style="Card.TFrame", padding=(10, 6))
            card.pack(side="left", fill="x", expand=True, padx=(0, 7))
            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            value = ttk.Label(card, text="0", style="Metric.TLabel")
            value.pack(anchor="w", pady=(2, 0))
            self.metric_labels.append(value)

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content, style="Card.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ttk.Frame(content, style="Card.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        views = ttk.Notebook(left)
        views.pack(fill="both", expand=True)
        summary_tab = ttk.Frame(views, style="Card.TFrame", padding=8)
        log_tab = ttk.Frame(views, style="Card.TFrame", padding=8)
        views.add(summary_tab, text="Current stock by SKU")
        views.add(log_tab, text="Movement log")

        ttk.Label(summary_tab, text="Current stock by SKU", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Label(summary_tab, text="Double-click an opening stock value to adjust it.", style="Sub.TLabel").pack(anchor="w", pady=(0, 7))
        self.summary = ttk.Treeview(summary_tab, columns=("product", "sku", "opening", "in", "out", "current"), show="headings", height=15)
        for col, title, width in [("product", "Product", 170), ("sku", "SKU", 80), ("opening", "Opening", 90), ("in", "Stock In", 90), ("out", "Stock Out", 90), ("current", "Current Stock", 110)]:
            self.summary.heading(col, text=title)
            self.summary.column(col, width=width, anchor="w" if col == "product" else "center", stretch=True)
        summary_scroll = ttk.Scrollbar(summary_tab, orient="vertical", command=self.summary.yview)
        self.summary.configure(yscrollcommand=summary_scroll.set)
        self.summary.pack(side="left", fill="both", expand=True)
        summary_scroll.pack(side="right", fill="y")
        self.summary.bind("<Double-1>", self.edit_opening)

        log_header = ttk.Frame(log_tab, style="Card.TFrame")
        log_header.pack(fill="x", pady=(0, 7))
        ttk.Label(log_header, text="Stock movement history", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(log_header, text="Export CSV", command=self.export_csv).pack(side="right")
        ttk.Button(log_header, text="Delete selected", command=self.delete_selected).pack(side="right", padx=(0, 7))
        cols = ("date", "product", "sku", "type", "qty", "unit_price", "sale_amount", "party", "reference")
        self.log = ttk.Treeview(log_tab, columns=cols, show="headings", height=15)
        headings = [("date", "Date", 85), ("product", "Product", 110), ("sku", "SKU", 55), ("type", "Type", 55), ("qty", "Qty", 50), ("unit_price", "Price/packet ₹", 90), ("sale_amount", "Sale total ₹", 90), ("party", "Party / Notes", 130), ("reference", "Reference", 85)]
        for col, title, width in headings:
            self.log.heading(col, text=title)
            self.log.column(col, width=width, anchor="w" if col in ("date", "product", "party", "reference") else "center", stretch=True)
        log_scroll = ttk.Scrollbar(log_tab, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        self.log.tag_configure("out", foreground="#a33a36")

        ttk.Label(right, text="Add stock movement", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        self.date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        self.product_var = tk.StringVar(value=list(PRODUCT_SKUS)[0])
        self.sku_var = tk.StringVar(value=PRODUCT_SKUS[list(PRODUCT_SKUS)[0]][0])
        self.type_var = tk.StringVar(value="IN")
        self.qty_var = tk.StringVar()
        self.price_var = tk.StringVar()
        self.party_var = tk.StringVar()
        self.ref_var = tk.StringVar()
        fields = [
            ("Date", self.date_var, "entry"),
            ("Product", self.product_var, "product"),
            ("SKU", self.sku_var, "sku"),
            ("Movement", self.type_var, "movement"),
            ("Quantity (packets)", self.qty_var, "entry"),
            ("Actual price per packet ₹ (optional)", self.price_var, "entry"),
            ("Party / Notes", self.party_var, "entry"),
            ("Reference", self.ref_var, "entry"),
        ]
        for row_index, (label, var, kind) in enumerate(fields):
            cell = ttk.Frame(right, style="Card.TFrame")
            cell.pack(fill="x", pady=(0, 5))
            ttk.Label(cell, text=label, style="Sub.TLabel").pack(anchor="w", pady=(0, 2))
            if kind == "product":
                widget = ttk.Combobox(cell, textvariable=var, values=list(PRODUCT_SKUS), state="readonly")
                widget.bind("<<ComboboxSelected>>", self.product_changed)
            elif kind == "sku":
                widget = ttk.Combobox(cell, textvariable=var, values=PRODUCT_SKUS[self.product_var.get()], state="readonly")
            elif kind == "movement":
                widget = ttk.Combobox(cell, textvariable=var, values=["IN", "OUT"], state="readonly")
            else:
                widget = ttk.Entry(cell, textvariable=var)
            widget.pack(fill="x")

        ttk.Label(right, text="For OUT entries, blank price uses ₹100 per packet.", style="Sub.TLabel", wraplength=360).pack(anchor="w", pady=(0, 8))
        entry_buttons = ttk.Frame(right, style="Card.TFrame")
        entry_buttons.pack(fill="x")
        ttk.Button(entry_buttons, text="Add movement", style="Accent.TButton", command=self.add_movement).pack(side="left", fill="x", expand=True)
        ttk.Button(entry_buttons, text="Clear", command=self.clear_form).pack(side="left", padx=(7, 0))

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(7, 0))
        ttk.Label(footer, text="Opening stock follows the reference workbook: 21 packets per SKU.", style="Sub.TLabel").pack(side="left")
        self.save_status = ttk.Label(footer, text="", style="Sub.TLabel")
        self.save_status.pack(side="right")

    def show_all_stock(self):
        balances = self.balances()
        total_current = sum(row["opening"] + row["in"] - row["out"] for row in balances.values())
        window = tk.Toplevel(self)
        window.title("Current total stock")
        window.geometry("850x440")
        window.transient(self)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Current total stock", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"All products and SKUs · {total_current:,} packets remaining", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(6, 12))
        columns = ("product", "sku", "opening", "in", "out", "current")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        for col, label, width in [("product", "Product", 200), ("sku", "SKU", 100), ("opening", "Opening", 110), ("in", "Stock In", 110), ("out", "Stock Out", 110), ("current", "Current Stock", 130)]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w" if col == "product" else "center", stretch=True)
        tree.pack(fill="both", expand=True)
        for row in balances.values():
            current = row["opening"] + row["in"] - row["out"]
            tree.insert("", "end", values=(row["product"], row["sku"], row["opening"], row["in"], row["out"], current))
        tree.insert("", "end", values=("TOTAL", "", sum(r["opening"] for r in balances.values()), sum(r["in"] for r in balances.values()), sum(r["out"] for r in balances.values()), total_current), tags=("total",))
        tree.tag_configure("total", font=("Segoe UI", 10, "bold"), background="#e8eef3")

    def show_product(self, product):
        balances = self.balances()
        rows = [balances[self.key(product, sku)] for sku in PRODUCT_SKUS[product]]
        total_current = sum(row["opening"] + row["in"] - row["out"] for row in rows)
        window = tk.Toplevel(self)
        window.title(f"{product} · Stock overview")
        window.geometry("650x380")
        window.transient(self)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=product, style="Title.TLabel").pack(anchor="w")
        total_sales = sum(row.get("sales", 0.0) for row in rows)
        ttk.Label(frame, text=f"Total remaining across all SKUs: {total_current:,} packets\nTotal sales: ₹{total_sales:,.2f}", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(8, 14))
        tree = ttk.Treeview(frame, columns=("sku", "opening", "in", "out", "sold", "sales", "current"), show="headings", height=6)
        for col, label, width in [("sku", "SKU", 80), ("opening", "Opening", 85), ("in", "Stock In", 85), ("out", "Stock Out", 90), ("sold", "Sold", 75), ("sales", "Sales ₹", 100), ("current", "Remaining", 100)]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="center")
        tree.pack(fill="both", expand=True)
        for row in rows:
            current = row["opening"] + row["in"] - row["out"]
            sold = row.get("sold", 0)
            sales = row.get("sales", 0.0)
            tree.insert("", "end", values=(row["sku"], row["opening"], row["in"], row["out"], sold, f"₹{sales:,.2f}", current))
    def product_changed(self, _event=None):
        product = self.product_var.get()
        for child in self.winfo_children():
            pass
        # The SKU selector is the third input widget in the entry row.
        self.sku_var.set(PRODUCT_SKUS[product][0])
        for widget in self.winfo_children():
            self._update_sku_combobox(widget, product)

    def _update_sku_combobox(self, widget, product):
        if isinstance(widget, ttk.Combobox) and str(widget.cget("textvariable")) == str(self.sku_var):
            widget.configure(values=PRODUCT_SKUS[product])
        for child in widget.winfo_children():
            self._update_sku_combobox(child, product)

    def add_movement(self):
        raw_date = self.date_var.get().strip()
        product, sku, movement = self.product_var.get(), self.sku_var.get(), self.type_var.get()
        try:
            datetime.strptime(raw_date, "%Y-%m-%d")
            quantity = int(self.qty_var.get().strip())
            if quantity <= 0:
                raise ValueError
            if movement == "OUT":
                price_text = self.price_var.get().strip().replace(",", "")
                unit_price = float(price_text) if price_text else DEFAULT_SELL_PRICE
                if unit_price < 0:
                    raise ValueError
            else:
                unit_price = None
        except ValueError:
            messagebox.showerror("Check the entry", "Enter a valid date (YYYY-MM-DD) and a positive whole-number quantity.")
            return
        if product not in PRODUCT_SKUS or sku not in PRODUCT_SKUS[product] or movement not in ("IN", "OUT"):
            messagebox.showerror("Check the entry", "Choose a valid product, SKU, and movement type.")
            return
        movement_row = {
            "id": datetime.now().strftime("%Y%m%d%H%M%S%f"), "date": raw_date,
            "product": product, "sku": sku, "type": movement, "quantity": quantity,
            "unit_price": unit_price,
            "sale_amount": quantity * unit_price if movement == "OUT" else None,
            "party": self.party_var.get().strip(), "reference": self.ref_var.get().strip(),
        }
        self.data["movements"].append(movement_row)
        self.save_data()
        self.refresh()
        self.qty_var.set("")
        self.price_var.set("")
        self.party_var.set("")
        self.ref_var.set("")
        self.qty_var._entry.focus_set() if hasattr(self.qty_var, "_entry") else None

    def clear_form(self):
        self.date_var.set(date.today().strftime("%Y-%m-%d"))
        self.qty_var.set("")
        self.price_var.set("")
        self.party_var.set("")
        self.ref_var.set("")

    def balances(self):
        result = {}
        for product, skus in PRODUCT_SKUS.items():
            for sku in skus:
                k = self.key(product, sku)
                result[k] = {"product": product, "sku": sku, "opening": int(self.data["opening"].get(k, DEFAULT_OPENING)), "in": 0, "out": 0, "sold": 0, "sales": 0.0}
        for row in self.data["movements"]:
            k = self.key(row.get("product", ""), row.get("sku", ""))
            if k in result:
                if row.get("type") == "IN":
                    result[k]["in"] += int(row.get("quantity", 0))
                else:
                    qty = int(row.get("quantity", 0))
                    result[k]["out"] += qty
                    result[k]["sold"] += qty
                    result[k]["sales"] += stock_out_value(row)
        return result

    def refresh(self):
        balances = self.balances()
        for item in self.summary.get_children():
            self.summary.delete(item)
        total_current = total_in = total_out = total_sales = 0
        for k, row in balances.items():
            current = row["opening"] + row["in"] - row["out"]
            total_current += current
            total_in += row["in"]
            total_out += row["out"]
            total_sales += row["sales"]
            self.summary.insert("", "end", iid=k, values=(row["product"], row["sku"], row["opening"], row["in"], row["out"], current))
        self.metric_labels[0].configure(text=f"{total_current:,}")
        self.metric_labels[1].configure(text=f"{total_out:,}")
        self.metric_labels[2].configure(text=f"{total_in:,}")
        self.metric_labels[3].configure(text=f"₹{total_sales:,.2f}")
        for item in self.log.get_children():
            self.log.delete(item)
        rows = sorted(self.data["movements"], key=lambda r: (r.get("date", ""), r.get("id", "")), reverse=True)
        for row in rows:
            sale_value = f"₹{stock_out_value(row):,.2f}" if row.get("type") == "OUT" else ""
            self.log.insert("", "end", iid=row["id"], values=(row.get("date", ""), row.get("product", ""), row.get("sku", ""), row.get("type", ""), row.get("quantity", 0), f"₹{float(row.get('unit_price') if row.get('unit_price') is not None else DEFAULT_SELL_PRICE):,.2f}" if row.get("type") == "OUT" else "", sale_value, row.get("party", ""), row.get("reference", "")), tags=("out",) if row.get("type") != "IN" else ())

    def edit_opening(self, event):
        item = self.summary.identify_row(event.y)
        col = self.summary.identify_column(event.x)
        if not item or col != "#3":
            return
        row = self.balances()[item]
        value = tk.simpledialog.askinteger("Opening stock", f"Set opening stock for {row['product']} {row['sku']}:", initialvalue=row["opening"], minvalue=0, parent=self)
        if value is not None:
            self.data["opening"][item] = value
            self.save_data()
            self.refresh()

    def delete_selected(self):
        selected = self.log.selection()
        if not selected:
            messagebox.showinfo("Movement log", "Select one or more movement rows to delete.")
            return
        if not messagebox.askyesno("Delete movements", f"Delete {len(selected)} selected movement(s)?"):
            return
        ids = set(selected)
        self.data["movements"] = [r for r in self.data["movements"] if r.get("id") not in ids]
        self.save_data()
        self.refresh()

    def export_csv(self):
        path = filedialog.asksaveasfilename(title="Export movement log", defaultextension=".csv", initialfile="siloti_stock_movements.csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for row in sorted(self.data["movements"], key=lambda r: (r.get("date", ""), r.get("id", ""))):
                writer.writerow({field: (DEFAULT_SELL_PRICE if field == "unit_price" and row.get("type") == "OUT" and row.get("unit_price") is None else stock_out_value(row) if field == "sale_amount" and row.get("type") == "OUT" else row.get(field, "")) for field in FIELDS})
        messagebox.showinfo("Export complete", f"Movement log exported to:\n{path}")


if __name__ == "__main__":
    from tkinter import simpledialog
    tk.simpledialog = simpledialog
    StockTool().mainloop()


