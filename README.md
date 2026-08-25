# Wearable Health & Shopping App

A full-stack mobile assessment project: a **Flutter** app for a wearable health
tracker (mock BLE device) with an integrated **product store**, backed by a
**FastAPI** REST API with **JWT auth**, **Alembic** migrations, and a live
**MySQL** database hosted on **Aiven**. The backend is deployed on **Render**.

| Layer      | Stack                                                              |
|------------|---------------------------------------------------------------------|
| Mobile     | Flutter, Riverpod, Dio, SQLite (sqflite), fl_chart                 |
| Backend    | FastAPI, SQLAlchemy 2.0, Alembic, JWT (python-jose), bcrypt         |
| Database   | MySQL (Aiven, managed/cloud)                                        |
| Hosting    | Render (Web Service) — backend, `https://erbrains.onrender.com`     |

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Backend (FastAPI)](#backend-fastapi)
  - [Project Structure](#backend-project-structure)
  - [Database Schema](#database-schema)
  - [Migrations (Alembic)](#migrations-alembic)
  - [Authentication](#authentication)
  - [API Endpoints](#api-endpoints)
  - [Local Setup](#backend-local-setup)
  - [Deployment (Render + Aiven)](#deployment-render--aiven)
- [Mobile App (Flutter)](#mobile-app-flutter)
  - [Project Structure](#flutter-project-structure)
  - [State Management (Riverpod)](#state-management-riverpod)
  - [Offline-First Storage & Sync](#offline-first-storage--sync)
  - [Features](#features)
  - [Local Setup](#flutter-local-setup)
- [Demo Credentials](#demo-credentials)

---

## Architecture Overview

```
┌─────────────────────────┐         HTTPS / JSON        ┌──────────────────────────┐
│        Flutter App      │ ───────────────────────────▶│      FastAPI Backend     │
│  (Riverpod + SQLite)    │◀─────────────────────────── │   (Render Web Service)   │
└─────────────────────────┘                              └──────────────────────────┘
        │  local cache                                              │
        ▼  (offline queue)                                          ▼
┌─────────────────────────┐                              ┌──────────────────────────┐
│   sqflite (on-device)   │                              │   MySQL on Aiven Cloud   │
└─────────────────────────┘                              └──────────────────────────┘
```

- The wearable is **simulated** (`MockWearableService`) so the app can be
  graded without real hardware. It streams heart rate / SpO₂ / step readings
  on a timer and behaves like a real BLE integration point (connect,
  disconnect, reconnect, random dropouts).
- Every reading is written to **local SQLite first**. If the device is
  online, it is pushed to the backend right after; if offline, it stays
  queued locally (`synced = 0`) until connectivity returns, then a background
  sync flushes the backlog in batches.
- The backend exposes a small e-commerce module (products, cart, orders) in
  addition to the health-tracking API, backed by the same MySQL database.

---

## Backend (FastAPI)

### Backend Project Structure

```
app/
├── main.py                 # FastAPI app, CORS, router registration, error handler
├── deps.py                 # get_current_user() — JWT auth dependency
├── seed.py                 # Seeds demo products + a demo user/device/history
├── core/
│   ├── config.py           # Reads DATABASE_URL / JWT_SECRET from .env
│   └── security.py         # bcrypt hashing + JWT create/decode
├── db/
│   ├── connection.py       # SQLAlchemy engine, session, Base, init_db()
│   └── model.py            # ORM models (User, Device, HealthReading, Product, CartItem, Order, OrderItem)
├── routers/
│   ├── auth.py              # /auth/register, /auth/login
│   ├── devices.py           # /devices (CRUD for paired wearables)
│   ├── health.py            # /health/readings, /health/readings/batch, /health/summary
│   ├── products.py          # /products (public storefront listing)
│   ├── cart.py               # /cart (add/update/remove)
│   └── orders.py             # /orders (checkout, order history)
└── schemas/                 # Pydantic request/response models, one file per domain

alembic/
├── env.py                   # Wires Alembic to the same DATABASE_URL as the app
└── versions/
    └── 8c82250066b3_initial_schema.py   # The one and only migration so far — creates all 7 tables
```

### Database Schema

| Table            | Purpose                                                                 |
|-------------------|--------------------------------------------------------------------------|
| `users`           | Account, email (unique), bcrypt password hash                          |
| `devices`         | A wearable paired to a user (`device_id` is the hardware/mock ID)      |
| `health_readings` | Heart rate / SpO₂ / steps / battery per device, timestamped            |
| `products`        | Storefront catalog                                                     |
| `cart_items`      | One row per (user, product) — quantity                                 |
| `orders`          | A checked-out cart, with a total and status                            |
| `order_items`     | Line items of an order, price frozen at purchase time                  |

Notable design choices:
- `health_readings` has a **unique constraint on `(device_id, client_reading_id)`**.
  The Flutter client generates a UUID for every reading before it's even
  synced, so retrying a failed sync (e.g. after a dropped connection) never
  creates duplicate rows on the server — the second insert is simply ignored.
- `ix_health_readings_user_recorded` (composite index on `user_id, recorded_at`)
  keeps the history/graph queries (`/health/readings`, `/health/summary`) fast
  as the table grows.
- All foreign keys use `ON DELETE CASCADE` so deleting a user/device cleans up
  its dependent rows automatically.

### Migrations (Alembic)

This project uses **Alembic** for schema version control instead of relying
on SQLAlchemy's `create_all()` in production.

- **`alembic/env.py`** — configured to read the same `DATABASE_URL` the app
  uses (from `.env`), so migrations always target the real database, not a
  hardcoded one.
- **`alembic/versions/8c82250066b3_initial_schema.py`** — the initial (and
  currently only) migration. It creates all 7 tables above, in dependency
  order, with their indexes, unique constraints, and foreign keys. This is
  the file that was actually run against the live Aiven MySQL database.

To apply migrations:

```bash
alembic upgrade head        # apply all pending migrations
alembic downgrade -1        # roll back the last migration
alembic revision --autogenerate -m "describe change"   # create a new migration after editing app/db/model.py
```

> `app/db/connection.py::init_db()` still exists and can call `Base.metadata.create_all()`
> for quick local prototyping, but the source of truth for any real
> environment (including the live Render deployment) is `alembic upgrade head`.

### Authentication

- `POST /auth/register` — creates a user, hashes the password with **bcrypt**.
- `POST /auth/login` — verifies the password and returns a **JWT access token**
  (`HS256`, configurable expiry via `JWT_EXPIRE_MINUTES`, default 24h).
- All protected routes read `Authorization: Bearer <token>` and resolve it to
  the current `User` row via `app/deps.py::get_current_user`.

### API Endpoints

| Method | Path                     | Auth | Description                                        |
|--------|--------------------------|------|------------------------------------------------------|
| POST   | `/auth/register`         | –    | Create an account                                    |
| POST   | `/auth/login`             | –    | Log in, get a JWT                                    |
| GET    | `/health`                 | –    | Health check (uptime probe for Render)               |
| POST   | `/devices`                 | ✅   | Register / re-link a wearable to the current user     |
| GET    | `/devices`                 | ✅   | List the current user's devices                      |
| PATCH  | `/devices/{id}`            | ✅   | Update battery / connection status / name             |
| DELETE | `/devices/{id}`            | ✅   | Unpair a device                                       |
| POST   | `/health/readings`         | ✅   | Push a single reading                                 |
| POST   | `/health/readings/batch`   | ✅   | Push many queued readings at once (offline sync)      |
| GET    | `/health/readings`         | ✅   | Paginated reading history, filterable by device/date  |
| GET    | `/health/summary`          | ✅   | Aggregated avg HR / SpO₂ / total steps (daily/weekly) |
| GET    | `/products`                 | –   | List products (public storefront)                    |
| GET    | `/products/{id}`            | –   | Product detail                                        |
| POST   | `/cart`                     | ✅   | Add a product to the cart                             |
| GET    | `/cart`                     | ✅   | View cart + running total                             |
| PATCH  | `/cart/{item_id}`           | ✅   | Change quantity                                        |
| DELETE | `/cart/{item_id}`           | ✅   | Remove an item                                         |
| POST   | `/orders`                    | ✅   | Checkout — turns the cart into an order, decrements stock |
| GET    | `/orders`                    | ✅   | Order history                                          |

Interactive docs are auto-generated by FastAPI at `/docs` (Swagger UI) and
`/redoc` once the server is running.

### Backend Local Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env
DATABASE_URL=mysql+pymysql://user:password@host:port/dbname
JWT_SECRET=change-me
JWT_EXPIRE_MINUTES=1440

alembic upgrade head          # create all tables
python -m app.seed            # optional: seed demo products + demo user
uvicorn app.main:app --reload
```

### Deployment (Render + Aiven)

- **Database:** a MySQL instance provisioned through the **Aiven console**.
  The connection string (with SSL params as required by Aiven) is stored in
  `DATABASE_URL` and never committed — it's injected as an environment
  variable.
- **API:** deployed as a **Render Web Service**, pointed at this GitHub repo.
  Render builds the service, injects the same environment variables
  (`DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`), and runs
  `alembic upgrade head` before starting `uvicorn` so the live schema is
  always in sync with the migration history.
- The Flutter app's base URL points at the deployed instance:
  `https://erbrains.onrender.com` (see `lib/core/constants/api_constants.dart`).

---

## Mobile App (Flutter)

### Flutter Project Structure

Feature-first architecture — each feature owns its `data` (models, remote/
local sources, repository) and `presentation` (view + Riverpod viewmodel):

```
lib/
├── main.dart
├── core/
│   ├── network/          # Dio client + typed ApiException
│   ├── storage/           # sqflite AppDatabase, SharedPreferences token storage
│   ├── constants/          # API base URL & route paths
│   ├── theme/
│   └── utils/              # connectivity_provider (online/offline stream)
├── features/
│   ├── auth/                # login / register
│   ├── device/               # pairing (mock BLE scan) + live dashboard
│   ├── history/               # readings history + weekly/daily graphs (fl_chart)
│   ├── shop/                   # products, cart, orders
│   └── sync/                    # offline → online sync repository
└── widgets/                     # shared UI (app scaffold/bottom nav)
```

### State Management (Riverpod)

Every feature follows the same pattern:
`View` → watches a `ViewModel` (a `StateNotifier`/`AsyncNotifier` provider) →
which calls a `Repository` → which calls a `RemoteSource` (Dio/HTTP) and/or
a `LocalSource` (sqflite). This keeps the UI free of business logic and
makes each layer independently testable.

### Offline-First Storage & Sync

- **Local DB:** `sqflite` table `health_readings` with a `synced` flag and a
  `UNIQUE` constraint on `reading_uid` (`deviceId + timestamp`), so writes
  from the mock wearable are never lost even without a connection.
- **Connectivity:** `connectivity_plus` exposes an `isOnlineProvider` the UI
  and sync logic both watch.
- **Sync flow** (`SyncRepository.syncPendingReadings`):
  1. Read all rows where `synced = 0` from SQLite.
  2. For each, look up the server-side numeric `device_id` (returned when the
     device was registered via `POST /devices`).
  3. Push it to `/health/readings`; only mark it `synced = 1` **after** a
     confirmed success response — so a crash mid-sync never loses data or
     silently drops a reading.
  4. If a request fails for a connectivity reason, the batch stops early and
     retries as a whole the next time sync runs, instead of hammering the API.

### Features

- **Auth** — register/login, JWT stored via `SharedPreferences`, attached
  automatically to every request by a Dio interceptor.
- **Device pairing** — mock BLE scan (`MockBleScanner`) lists nearby fake
  devices; connecting starts a simulated reading stream with realistic
  behavior (connect delay, ~10% connect failure, ~5% random mid-session
  drop, auto-reconnect, battery drain over time).
- **Dashboard** — live heart rate / SpO₂ / steps / battery cards, sourced
  from the current wearable stream.
- **History** — tabbed view of raw readings plus **daily/weekly graphs**
  built with `fl_chart`, pulling aggregated data from `/health/summary`
  and paginated detail from `/health/readings`.
- **Shop** — product listing, product detail, cart (add/update/remove), and
  checkout into an order, all backed by the live backend.

### Flutter Local Setup

```bash
cd frontend   # wherever pubspec.yaml lives
flutter pub get
flutter run
```

Update `lib/core/constants/api_constants.dart` if you're pointing at a
different backend (e.g. `http://10.0.2.2:8000` for a local server on the
Android emulator) instead of the live Render URL.

---

## Demo Credentials

The backend can be seeded with a ready-to-use demo account (`python -m app.seed`):

| Field    | Value                 |
|----------|------------------------|
| Email    | `demo@erbrains.com`   |
| Password | `demo1234`             |

This also seeds sample products, a paired demo device, ~3 days of health
history, one cart item, and one completed order — so every screen has real
data to show immediately.
