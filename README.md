# Docker-Archiver

**Project Overview**
- **Description:** Docker-Archiver is a small Flask web application that helps you archive Docker Compose stacks. It stops a stack, creates a TAR archive of the stack directory, restarts the stack, and stores archive metadata and job logs in a PostgreSQL database.

**Key Features**
- **Web UI:** Dashboard for discovering local stacks, starting archives, and viewing recent or full history.
- **Archive stacks:** Stops a Docker Compose stack, creates a .tar archive of the stack directory, then restarts the stack.
- **Background jobs & logging:** Archiving runs in background threads; each job is recorded in the `archive_jobs` table with logs appended during the process.
-- **Archive storage:** Archives are stored inside the container at `/archives` (mounted to a host path via Docker volumes in `docker-compose.yml`).
- **Retention cleanup:** Configurable retention (default 28 days) removes old `.tar` archives.
- **User management:** Initial setup for the first admin user, profile edit, and password change via the web UI.
- **Passkeys (WebAuthn):** Register and authenticate using passkeys (WebAuthn) in addition to password login.
- **Download & delete archives:** UI endpoints to download or delete specific archive files.
- **Postgres-backed settings:** Stores settings, users, passkeys and job metadata in Postgres.

**Important Files**
- **App entry & routes:** [app/main.py](app/main.py)
- **Archiving logic:** [app/backup.py](app/backup.py)
- **Dockerfile:** [Dockerfile](Dockerfile)
- **Docker Compose:** [docker-compose.yml](docker-compose.yml)
- **Python requirements:** [requirements.txt](requirements.txt)
- **Templates:** [app/static/templates](app/static/templates)

**Installation (Recommended: Docker)**
- Start with Docker Compose (recommended):

```bash
docker-compose up -d --build
```

- The default `docker-compose.yml` binds:
	- host Docker socket (`/var/run/docker.sock`) into the container
	- host stack directories under `/opt/stacks` or `/opt/dockge` into `/local` inside the container
	- backup directory `/var/backups/docker` (host) mounted to `/archives` (container) to persist archives

**Local development (without Docker)**
- Ensure `DATABASE_URL` is set to a running Postgres instance, then install dependencies and run:

```bash
pip install -r requirements.txt
python -m app.main
```

or run with Gunicorn (as the Dockerfile does):

```bash
# install dependencies
pip install -r requirements.txt
# run with gunicorn
gunicorn --bind 0.0.0.0:5000 main:app
```

**Configuration**
- Environment variables:
	- **DATABASE_URL:** PostgreSQL connection string (required).
- Important code-level defaults:
	- `LOCAL_STACKS_PATH` (in [app/main.py](app/main.py)) defaults to `/local` — the directory scanned for stacks.
	- `CONTAINER_BACKUP_DIR` (in [app/main.py](app/main.py)) defaults to `/archives` inside the container.
	- WebAuthn settings (`RP_ID`, `ORIGIN`) are set in [app/main.py](app/main.py) and should be updated for production.

**Usage**
- Open the web UI (default http://localhost:5000). On first run you'll be prompted to create the initial admin user.
- The dashboard lists discovered stacks (directories containing `docker-compose.yml` or `compose.yaml` under `LOCAL_STACKS_PATH`).
- Select one or more stacks, set the retention days, and start archiving. The process runs in background and you can view logs and history in the UI.

**Security & Notes**
- This project currently uses simple session-based authentication and optional WebAuthn passkeys; secure `SECRET_KEY`, `DATABASE_URL`, and WebAuthn `RP_ID/ORIGIN` before production use.
- The app invokes system commands (`docker`, `tar`) and requires the container or host to have these available.

**License & Contributing**
- See the repository `LICENSE` for licensing details. Contributions and issues are welcome.

---

If you'd like, I can also:
- add example environment files,
- add more detailed run/backup examples, or
- update the README to include screenshots of the UI.
