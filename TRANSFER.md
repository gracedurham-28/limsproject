Project transfer checklist and commands

1) Copy the project folder to the new machine.

2) Create and activate a venv (zsh):
   python3 -m venv limsenv
   source limsenv/bin/activate

3) Install dependencies:
   pip install --upgrade pip
   pip install -r requirements.txt

4) Create a .env from .env.example and set secrets
   cp .env.example .env
   # edit .env and set DJANGO_SECRET_KEY, DB credentials etc
   export $(cat .env | xargs)

5) Prepare static files (so admin CSS works):
   python manage.py collectstatic --noinput

6) Run migrations and create a superuser if needed:
   python manage.py migrate
   python manage.py createsuperuser

7) Run the dev server:
   python manage.py runserver

## Start/Stop helper scripts

Two scripts are provided in `scripts/`:

- `scripts/start_server.sh` — starts the Django dev server in the background and writes `.runserver.pid`.
- `scripts/stop_server.sh` — stops the server using the PID file.

Make scripts executable:

```zsh
chmod +x scripts/start_server.sh scripts/stop_server.sh
```

Start server:

```zsh
./scripts/start_server.sh
```

Stop server:

```zsh
./scripts/stop_server.sh
```

## Database export / restore (Postgres)

Two helper scripts are provided in `scripts/` to export and restore Postgres databases:

- `scripts/db_export.sh [outdir]` — creates `outdir/app_db.dump` (pg_dump custom format) and `outdir/db_globals.sql`.
- `scripts/db_restore.sh [dumpdir]` — restores the database and globals from `dumpdir`.

Usage example (source machine):

```zsh
# create a directory for dumps
mkdir -p db_dumps
# use .env values if present
./scripts/db_export.sh db_dumps
# archive project + dumps for transfer
tar -czf appsett_full_export.tgz --exclude='limsenv' --exclude='logs' --exclude='*.pyc' . db_dumps
```

Usage example (target machine):

```zsh
# extract archive and go to project dir
tar -xzf appsett_full_export.tgz
cd appsett
# create venv and install deps
python3 -m venv limsenv
source limsenv/bin/activate
pip install -r requirements.txt
# create .env and edit POSTGRES_* to match target Postgres superuser
cp .env.example .env
# restore DB dumps
./scripts/db_restore.sh db_dumps
# migrate and collect static
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver
```

Notes:
- The restore scripts use `pg_restore`/`psql` and require Postgres client tools to be installed on the machine performing the restore.
- If the dump contains CREATE DATABASE, `pg_restore -C` is used to recreate the database. Otherwise create the DB first and run `pg_restore -d <db>`.

## Docker option

See `docker-compose.yml` and `Dockerfile` — use these for a fully-contained reproducible setup:

```zsh
docker compose up -d --build
# optionally restore dump into running db container
docker cp db_dumps/app_db.dump $(docker compose ps -q db):/tmp/app_db.dump
docker compose exec db pg_restore -U postgres -d postgres /tmp/app_db.dump --clean --create
```

Notes:
- This project uses WhiteNoise to serve static files in production and in ASGI mode.
- If you prefer a production server, use gunicorn for WSGI or uvicorn/daphne for ASGI.
- Make sure to update requirements.txt if you add packages.
