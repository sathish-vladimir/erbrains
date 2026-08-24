# ERBrains Assessment — Backend (FastAPI)

Backend for the "Wearable Health & Shopping" take-home assignment.

**Stack deviation from the brief:** the assignment suggests Node.js/NestJS +
PostgreSQL. This implementation uses **FastAPI + SQLAlchemy + MySQL**
instead. Reasoning: FastAPI/SQLAlchemy gives the same layered
architecture (routers → schemas → models → DB) with less boilerplate,
built-in OpenAPI docs, and native Pydantic validation, which was a better
fit for a 72-hour scope. MySQL was chosen because it was already the
target during local setup; the code has no MySQL-specific SQL (plain
SQLAlchemy ORM), so switching `DATABASE_URL` to Postgres works with no
code changes — only the driver (`psycopg2`) needs to be swapped in.

---

## 1. Architecture

```
Flutter app
    |
    v
FastAPI routers (app/routers/*)      <- HTTP layer, one file per resource
    |
    v
Pydantic schemas (app/schemas/*)     <- request/response validation & shape
    |
    v
SQLAlchemy models (app/db/model.py)  <- ORM layer, one class per table
    |
    v
MySQL (or any SQL DB via DATABASE_URL)
```

- **`app/main.py`** — creates the FastAPI app, wires CORS, mounts routers, runs `init_db()`/seed on startup.
- **`app/core/config.py`** — reads `.env` into a single `settings` object.
- **`app/core/security.py`** — password hashing (bcrypt) + JWT issue/verify.
- **`app/deps.py`** — `get_current_user` dependency, used by every protected route.
- **`app/db/connection.py`** — SQLAlchemy engine/session/Base.
- **`app/db/model.py`** — all 7 tables (users, devices, health_readings, products, cart_items, orders, order_items).
- **`app/schemas/*.py`** — Pydantic request/response models, one file per domain.
- **`app/routers/*.py`** — one router per resource (auth, devices, health, products, cart, orders).
- **`app/seed.py`** — inserts sample products on first run so `GET /products` isn't empty.
- **`alembic/`** — versioned schema migrations (see §5).
- **`tests/`** — pytest suite against an isolated SQLite file, no live DB needed.

This mirrors the mobile-side separation the assignment asks for
(Flutter → Wearable Service interface → Mock implementation): each layer
here only talks to the layer directly below it, so e.g. swapping MySQL
for Postgres, or SQLAlchemy for another ORM, wouldn't touch the routers.

---

## 2. Setup & run (local)

### Prerequisites
- Python 3.11+
- A running MySQL 8 server

### Steps

```bash
# 1. Create the database
mysql -u root -p -e "CREATE DATABASE assessment;"

# 2. Configure environment
cp .env.example .env
# edit .env if your MySQL user/password/host differ

# 3. Install dependencies
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4. Apply migrations (creates all tables)
alembic upgrade head

# 5. Run the API
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for interactive Swagger docs (every
endpoint below is documented and callable from there).

On startup the app also seeds 4 sample products plus a demo user with
data in every table, so you can test right away — see §9.

> Note: `init_db()` (in `app/db/connection.py`) also runs on every
> startup and will `CREATE TABLE IF NOT EXISTS` for convenience — but the
> source of truth for schema changes is Alembic (§5), not this
> auto-create. In a real deployment you'd rely on `alembic upgrade head`
> alone (that's what the `Procfile` does — see §10).

### Run the tests

```bash
pytest -v
```

Tests run against a throwaway local SQLite file (`test_run.db`), not your
MySQL database, so they're safe to run at any time.

---

## 3. API documentation

All endpoints are also live at `/docs` (Swagger) and `/redoc`.
Protected endpoints require `Authorization: Bearer <token>` from `/auth/login`.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | – | Create a user *(extra — spec assumes a user already exists to log in)* |
| POST | `/auth/login` | – | Returns a JWT |
| POST | `/devices` | Y | Register/update a wearable device for the current user |
| GET | `/devices` | Y | List current user's devices |
| PATCH | `/devices/{id}` | Y | Update battery/connection status *(extra)* |
| POST | `/health/readings` | Y | Store one reading (rejects duplicate `client_reading_id` per device) |
| POST | `/health/readings/batch` | Y | Store many readings in one call — used by the offline sync queue *(extra, see §6)* |
| GET | `/health/readings` | Y | Paginated reading history (`device_id`, `start`, `end`, `limit`, `offset`) |
| GET | `/health/summary` | Y | Aggregated stats (`period=daily\|weekly`): avg HR, avg SpO2, total steps |
| GET | `/products` | – | List products (public, storefront-style) |
| GET | `/products/{id}` | – | Product detail |
| POST | `/cart` | Y | Add a product to cart (merges quantity if already present) |
| GET | `/cart` | Y | View cart + computed total |
| PATCH | `/cart/{item_id}` | Y | Change quantity *(extra)* |
| DELETE | `/cart/{item_id}` | Y | Remove item *(extra)* |
| POST | `/orders` | Y | Place an order from the current cart (checks stock, decrements it, clears cart) |
| GET | `/orders` | Y | Order history with line items |
| GET | `/health` | – | Liveness check |

---

## 4. Database design

```
users --< devices --< health_readings
  |                        (device_id, client_reading_id) UNIQUE
  |--< cart_items >-- products
  `--< orders --< order_items >-- products
```

- **users**: `id, email (unique), password_hash, full_name, created_at`
- **devices**: `id, device_id (unique), user_id -> users, name, battery, connection_status, created_at`
- **health_readings**: `id, client_reading_id, user_id -> users, device_id -> devices, heart_rate, spo2, steps, battery, recorded_at, created_at`
  — `UNIQUE(device_id, client_reading_id)` is the duplicate-prevention mechanism for sync retries (see §6). Indexed on `(user_id, recorded_at)` for the History screen's date-range queries.
- **products**: `id, name, description, price, stock, image_url, created_at`
- **cart_items**: `id, user_id -> users, product_id -> products, quantity` — `UNIQUE(user_id, product_id)` so adding the same product twice increments quantity instead of creating a second row.
- **orders**: `id, user_id -> users, status, total_amount, created_at`
- **order_items**: `id, order_id -> orders, product_id -> products, quantity, unit_price` — price is copied at order time so historical orders aren't affected by later price changes.

All foreign keys to `users`/`devices`/`orders` cascade on delete, so removing a user cleans up their devices, cart, orders, and readings.

---

## 5. Migrations (Alembic)

The project uses Alembic for versioned schema changes (not just
`create_all`), so the schema history is explicit and reproducible. The
initial migration (`alembic/versions/8c82250066b3_initial_schema.py`) is
already included and creates all 7 tables.

```bash
# apply all migrations
alembic upgrade head

# after changing a model in app/db/model.py, generate the next migration
alembic revision --autogenerate -m "describe the change"

# review the generated file in alembic/versions/ before applying
alembic upgrade head
```

`alembic/env.py` reads `DATABASE_URL` from the same `.env` as the app, so
migrations always target whatever database the API itself is configured
for.

---

## 6. Wearable integration approach

The assignment's mock-to-real replacement path maps onto this backend as follows — the backend never talks to a wearable directly, it only receives readings the Flutter app has already collected:

```
Flutter Application
    |
Wearable Service / Interface   (Dart abstract class, e.g. WearableService)
    |
Mock Wearable Implementation   (generates readings on a timer, for this assignment)
    |                                    ^ same interface ^
    |                          Real Implementation later: Platform Channels
    |                          -> Native Bridge -> Android SDK (Kotlin) /
    |                            iOS SDK (Swift) -> the actual smart ring
    v
POST /health/readings  or  POST /health/readings/batch
```

Recommended replacement approach: **Flutter Platform Channels**, wrapped
behind the same `WearableService` interface the mock implements. This
keeps the swap to a single class (`RealWearableService implements
WearableService`) with zero changes to the rest of the app — UI, local
storage, and sync logic all depend on the interface, not the
implementation. A full native plugin package would only be worth the
extra overhead if the wearable integration were being reused across
multiple separate apps.

---

## 7. Offline synchronisation approach

```
Wearable readings -> local storage (SQLite/Hive on device) -> Sync Queue -> this API
```

- The mobile app is expected to keep writing readings to local storage
  regardless of connectivity, tagging each with a client-generated
  `client_reading_id` (e.g. a UUID) at creation time — not at sync time.
- When connectivity returns, the app flushes its queue via
  **`POST /health/readings/batch`**, sending everything accumulated
  while offline in one request (this directly covers the assignment's
  100-readings-while-offline scenario).
- **Duplicate prevention**: `health_readings` has
  `UNIQUE(device_id, client_reading_id)`. If a batch (or a single
  request) is retried after a timeout — where the server actually
  received it but the client never got the response — the insert is
  simply skipped instead of erroring the whole batch or creating a
  duplicate row. `POST /health/readings/batch` reports
  `{"created": [...], "duplicates_skipped": N}` so the app can safely
  clear its local queue up to the last acknowledged reading either way.
- **Retry after failure**: because readings are only removed from the
  local queue after a successful (or duplicate-confirmed) server
  response, a failed sync simply means "try again with the same queue
  next time connectivity is available" — no readings are lost.

---

## 8. Error handling

- **Duplicate health readings** -> `409 Conflict` on the single endpoint; silently counted in `duplicates_skipped` on the batch endpoint (a batch is expected to contain retries, so it shouldn't fail as a whole).
- **Auth failure** -> `401 Unauthorized` with `WWW-Authenticate: Bearer`; wrong password vs. unknown email are not distinguished in the response, to avoid leaking which emails are registered.
- **Ownership checks** -> a device or reading that exists but belongs to another user returns `404`, not `403`, so as not to confirm the resource's existence to someone who doesn't own it.
- **Validation errors** -> FastAPI/Pydantic auto-validates every request body; a custom exception handler in `main.py` flattens the response shape for easier parsing on the mobile side.
- **Checkout guardrails**: empty cart -> `400`; insufficient stock for any item -> `400` and nothing is written (checked before any row is inserted/updated).
- **Bluetooth/device disconnect and no-internet** are handled entirely client-side (this repo is the backend); the API's role is limited to accepting whatever the client eventually sends and being safe to retry against.

---

## 9. Testing

```bash
pytest -v
```

Focused on the areas where incorrect behaviour would cause data loss or
wrong business results, per the assignment's guidance (not aiming for 100%
coverage):

- `tests/test_health_readings.py` — single + batch ingestion, duplicate
  rejection, the 100-readings offline-sync scenario (including a *second*
  identical sync to prove it's idempotent), and cross-user device access.
- `tests/test_cart_and_orders.py` — cart totals, quantity merging,
  checkout decrementing stock and clearing the cart, and the two failure
  paths (empty cart, insufficient stock) leaving state untouched.
- `tests/test_auth.py` — register/login, duplicate email, wrong password, missing token.

---

## 10. Deployment

Deployed on **Railway** (railway.app) using Railway's native Python
build (Nixpacks) — no Docker involved. Railway detects `requirements.txt`,
installs dependencies, and runs the `Procfile`'s start command:

```
web: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`$PORT` is set automatically by Railway; `alembic upgrade head` runs the
migration before the server starts accepting traffic, every deploy.

**Steps:**
1. Push this project to a GitHub repo.
2. On railway.app → New Project → Deploy from GitHub repo, select the repo.
3. Add a MySQL database: same project → New → Database → Add MySQL.
   Railway provisions it and exposes connection details as variables.
4. On the API service → Variables tab, set:
   - `DATABASE_URL` = `mysql+pymysql://<user>:<password>@<host>:<port>/<database>`
     (build this from the MySQL service's connection variables Railway shows you)
   - `JWT_SECRET` = a real random secret (not the local dev default)
5. Railway builds and deploys automatically. Once live, `/docs` on the
   generated `https://<your-app>.up.railway.app` URL should load Swagger,
   same as local — that's the public URL the Flutter app points at.

CORS is currently wide open (`allow_origins=["*"]`) for ease of
development against an emulator/device — restrict this to the app's
actual origin(s) before a production deployment.

---

## 11. Major technical decisions & trade-offs

- **FastAPI over NestJS**: faster to build correctly within 72 hours; trade-off is deviating from the suggested stack (documented above).
- **JWT over session cookies**: simpler for a mobile client with no browser/cookie jar; trade-off is manual token expiry/refresh handling on the client (not implemented — tokens just expire after `JWT_EXPIRE_MINUTES`, no refresh-token flow, to keep scope in check).
- **Batch sync endpoint added beyond the spec's minimum list**: sending 100 individual `POST /health/readings` calls after reconnecting is both slow and easy to get wrong (partial failures mid-loop); one batch call with per-row duplicate handling is simpler for the client and atomic-enough for this use case.
- **Alembic in addition to `create_all`**: `create_all` is kept for local dev convenience (matches the original zip's behaviour), but Alembic is the real migration story — required for any environment where the schema needs to evolve without dropping data.
- **No payment gateway**: out of scope per the assignment; `POST /orders` finalizes on stock + cart state only.
