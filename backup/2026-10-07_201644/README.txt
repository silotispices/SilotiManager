SILOTI STOCK MANAGER

Run on Windows
- Double-click "Run Siloti Stock Manager.bat".
- The app uses the bundled Python runtime when available, or Python 3 installed on Windows. No pip packages are required.

Stock entry
- Choose the date, product, SKU, movement (IN or OUT), and packet quantity.
- For OUT, enter the actual selling price per packet if it differs from ₹100. Leave it blank to use ₹100 per packet.
- The app multiplies packet quantity by the per-packet price to calculate the sales total.
- Party / Notes and Reference are optional.
- Entries save automatically. Product buttons show the stock and sales totals across that product's SKUs.
- Double-click an Opening value in the summary to adjust it. Select movement rows and use Delete selected to remove mistakes.
- Use Export CSV to open or analyze the movement log in Excel.

The product and SKU list follows the supplied workbook. Opening balances start at 21 packets per SKU.
The app stores data in siloti_stock_data.json in this folder. Keep it with the app and make backups periodically.
