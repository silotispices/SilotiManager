SILOTI BUSINESS MANAGER — WEB VERSION

The website brings together Stock, Expenses, and Order & billing. All signed-in users share the same records.

Run locally on Windows
- Double-click "Run Siloti Stock Manager.bat". The browser opens at http://localhost:8000.
- On the first visit, create the administrator username and password. Passwords must contain at least 12 characters.
- Sign in with that admin account. Use Manage users to create or disable user accounts. Each account can use all three sections.
- Keep this computer running while people are using the website.
- If the admin password is forgotten, choose Forgot admin password? The one-time code is written to the server console/logs, expires after 10 minutes, and can only be used once. On Docker, view it with `docker compose logs -f stock-manager` (or include `-f compose.cloudflare.yaml` if using the Cloudflare override). This recovery requires access to the host; the app does not send recovery email.

Self-host for public internet access
- This folder includes a Dockerfile and compose.yaml. On your Linux server with Docker Compose installed, point a domain's DNS A/AAAA record to the server and allow inbound ports 80 and 443 through its firewall/router.
- Edit Caddyfile and replace stock.example.com with your domain. Run: docker compose up -d --build
- The included Caddy service automatically obtains HTTPS certificates and proxies requests to the app. The app port is only available inside the Docker network; do not publish port 8000 to the internet.
- The compose setup stores the database and HTTPS certificates in persistent Docker volumes and requires secure cookies, so keep it behind HTTPS.
- Visit the HTTPS domain and create the first administrator account. Use Manage users to create each additional login.
- Back up the Docker volume named for this Compose project and keep a copy off the server.

Use Cloudflare Tunnel instead of the included Caddy service
- Put this folder on your Linux server and install Docker Compose and cloudflared.
- In Cloudflare, make sure your domain is active, then open Networking > Tunnels and create a remotely managed tunnel. Copy its installation command/token and install cloudflared on the server as shown in the dashboard.
- Add a published application route to the tunnel. Set its hostname (for example, stock.yourdomain.com) and set the service URL to http://localhost:8000.
- On the server, start the app with: docker compose -f compose.yaml -f compose.cloudflare.yaml up -d --build stock-manager
- The override exposes the app only to localhost and disables the Caddy service. Cloudflare Tunnel provides the public HTTPS route. Create the first admin account at your new HTTPS hostname.
- Keep the tunnel token private. The server needs outbound access to Cloudflare; a restrictive firewall must allow Tunnel traffic on port 7844.

Stock
- Add a stock movement with the New movement button; close the form with ×. Use Multiple entries for a batch.
- Record stock IN and OUT by date, product, SKU, and quantity. Blank OUT price uses ₹100 per packet.
- The current-stock table keeps one row per product/SKU and totals all movements. Movement history keeps each individual transaction as a separate row for review and editing.
- Adjust opening balances by selecting the opening quantity. Each movement and expense row has Edit and Delete actions. Download stock, movement, or expense CSV files.
- Generating an order bill verifies available stock and records the bill items as stock OUT movements.

Expenses
- Record expenses by date and category, review overall and current-month totals, delete selected rows, and download a CSV.

Order & billing
- Add multiple product/SKU lines, quantities, MRP, and percentage discounts. Generate a printable bill and update stock in one transaction.

Data
- The first start imports existing balances, stock movements, and expenses from the JSON files in this folder.
- The website stores shared records in SQLite. Keep the database volume with the deployment and back it up regularly.
- The prior desktop application remains in siloti_stock_tool.py. This website does not modify silotiweb.
