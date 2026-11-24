# SilotiManager
This repo will help managing siloti stock movment, billing and siloti expenses

## Cloudflare Worker deployment

The repository now includes a Cloudflare Worker backend. The Worker serves the files in `web`, implements the app's API, and stores shared users, stock, expenses, and bills in D1. This build does not need the Python server or an always-on machine. The original Docker deployment remains available for local or self-hosted use.

### First deployment

1. Install Node.js and authenticate Wrangler with the Cloudflare account that owns the Worker:

   ```sh
   npx wrangler login
   ```

2. Create the D1 database:

   ```sh
   npx wrangler d1 create siloti-manager
   ```

   Copy the returned database ID into `wrangler.toml`, replacing `REPLACE_WITH_D1_DATABASE_ID`.

3. Create its tables and default product rows, then deploy:

   ```sh
   npx wrangler d1 migrations apply siloti-manager --remote
   npx wrangler deploy
   ```

4. Open the deployed `workers.dev` address or attach your own domain in the Cloudflare dashboard. The first visitor can create the administrator account, so keep the URL private until setup is complete.

### Keep existing records

To copy records from the current `siloti_stock.sqlite3` into D1, first apply the D1 migration. Then generate a private SQL import file and upload it:

```sh
python tools/export_sqlite_to_d1.py siloti_stock.sqlite3 d1-import.sql
npx wrangler d1 execute siloti-manager --remote --file=d1-import.sql
```

The SQL file contains password hashes and business records. Keep it private and delete it after a successful import. User accounts and passwords are retained; existing sessions are not imported, so everyone will sign in again. The Cloudflare Worker sends administrator recovery codes to Worker logs. Limit log access to trusted administrators. After migration, use the same admin username and password as before.

### Cloudflare configuration

`wrangler.toml` sets the static asset directory and binds D1. `database_id` is account-specific and must be filled in before deployment. The Worker uses HTTPS-only, HttpOnly session cookies and CSRF checks for writes. Cloudflare's Worker and D1 usage limits still apply to your account.
