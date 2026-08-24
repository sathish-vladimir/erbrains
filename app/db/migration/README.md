# Migration

Superseded by the top-level `alembic/` directory, which now contains the
real, versioned migrations for this project (see the main README, §5).

`app/db/connection.py::init_db()` still runs `create_all` on every app
startup purely for local-dev convenience (matches the original starter's
behaviour). For any environment where the schema needs to evolve without
losing data, use `alembic upgrade head` instead - that's what the
Dockerfile / docker-entrypoint.sh does.
