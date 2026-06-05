# Automated Compliance Report Generation

This project is a Flask application for defect-liability-period compliance reporting. It supports multiple roles, stores claim and defect metadata in PostgreSQL, collects defect evidence images, generates AI-assisted report text with Groq, and exports tribunal-style PDF reports with ReportLab.

The main application lives in [app/module3](app/module3). That is the folder you should use for day-to-day development and deployment.

## What the app does

- Homeowner users can save claim details, attach evidence photos, and add remarks to defects.
- Developer and Legal users can review defects, update statuses, and generate reports.
- Admin users can view the main dashboard plus audit history.
- The system generates an AI narrative and then exports a PDF report aligned to the selected language.

## Project Structure

- [app/module3/app.py](app/module3/app.py) is the Flask entry point.
- [app/module3/routes.py](app/module3/routes.py) contains the login, dashboard, evidence upload, status update, AI report, and PDF export routes.
- [app/module3/report_data.py](app/module3/report_data.py) loads case metadata from PostgreSQL and assembles the structured report payload.
- [app/module3/report_generator.py](app/module3/report_generator.py) sends the prompt to Groq and returns AI-generated report text.
- [app/module3/database/db.py](app/module3/database/db.py) opens the PostgreSQL connection.
- [app/module3/templates](app/module3/templates) contains the HTML pages.
- [app/module3/static](app/module3/static) contains the CSS, JavaScript, and images.

## Requirements

Before you run the app, install these:

- Python 3.12 or later
- PostgreSQL 13+ or another compatible PostgreSQL server
- Docker Desktop if you want to run using containers
- A Groq API key for AI report generation

## Configuration

The app reads environment variables from [app/module3/.env.example](app/module3/.env.example). Copy it to `.env` and fill in your values.

Minimum values you should set:

- `GROQ_API_KEY` - your Groq API key
- `DB_HOST` - PostgreSQL host, for example `localhost` or `host.docker.internal`
- `DB_PORT` - usually `5432`
- `DB_NAME` - database name, for example `compliance_db`
- `DB_USER` - database user, usually `postgres`
- `DB_PASSWORD` - PostgreSQL password
- `FLASK_SECRET_KEY` - a strong random secret for sessions
- `APP_PORT` - host port for Docker, default `5050`

Optional but useful:

- `APP_TIMEZONE` - default `Asia/Kuala_Lumpur`
- `SESSION_COOKIE_SECURE` - set to `1` only when using HTTPS
- `SESSION_IDLE_TIMEOUT_MINUTES` - session timeout in minutes
- `ENABLE_DEMO_LOGIN_FALLBACK` - keep `0` for production

## Database Setup

The application expects an existing PostgreSQL database with the core business tables already created. In particular, the app reads and writes data for users, defects, remarks, completion dates, evidence metadata, audit logs, and report profiles.

The SQL files in [app/module3/database](app/module3/database) are the main starting point:

- [app/module3/database/report_metadata.sql](app/module3/database/report_metadata.sql)
- [app/module3/database/user_profile_upserts.sql](app/module3/database/user_profile_upserts.sql)
- [app/module3/database/fix_status_pdf_consistency.sql](app/module3/database/fix_status_pdf_consistency.sql)

If you are deploying on a new machine, create the PostgreSQL database first, then import the required schema and seed data before starting the app.

## Local Run Without Docker

Use this if you want to run the Flask app directly on your machine.

1. Open a terminal in the repository root.
2. Create and activate a Python virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies.

```powershell
pip install -r requirements.txt
```

4. Go to the module3 folder and create the `.env` file.

```powershell
cd app\module3
Copy-Item .env.example .env
notepad .env
```

5. Fill in the PostgreSQL and Groq values in `.env`.
6. Make sure PostgreSQL is running and the database schema is imported.
7. Start the app.

```powershell
python app.py
```

8. Open the app in your browser.

```text
http://localhost:5000/login
```

## Run With Docker, Development Mode

This is the easiest way for new people to start the app.

1. Install Docker Desktop.
2. Start PostgreSQL and make sure it is reachable from Docker.
3. Open PowerShell and go to the module3 folder.

```powershell
cd app\module3
```

4. Copy the environment example file.

```powershell
Copy-Item .env.example .env
```

5. Edit `.env` and set your real values.

```text
GROQ_API_KEY=your_real_key
DB_HOST=host.docker.internal
DB_PORT=5432
DB_NAME=compliance_db
DB_USER=postgres
DB_PASSWORD=your_db_password
FLASK_SECRET_KEY=replace-this-with-a-strong-secret
APP_PORT=5050
```

6. If you have old environment values set in the current PowerShell session, clear them first.

```powershell
Remove-Item Env:DB_HOST -ErrorAction SilentlyContinue
Remove-Item Env:DB_PORT -ErrorAction SilentlyContinue
Remove-Item Env:DB_NAME -ErrorAction SilentlyContinue
Remove-Item Env:DB_USER -ErrorAction SilentlyContinue
Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue
```

7. Build and start the container.

```powershell
docker compose up -d --build
```

8. Check the container status.

```powershell
docker compose ps
docker compose logs --tail=100 app
```

9. Open the app.

```text
http://localhost:5050/login
```

10. Stop the app when you are done.

```powershell
docker compose down
```

## Run With Docker, Production Mode

Use this when you want Gunicorn and a production-style configuration.

1. Go to [app/module3](app/module3).
2. Make sure `.env` is present and filled in.
3. Start the production compose file.

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

4. Check the status and logs.

```powershell
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 app
```

5. Open the app.

```text
http://localhost:5050/login
```

6. Stop the production container.

```powershell
docker compose -f docker-compose.prod.yml down
```

## Windows Shortcut Scripts

Inside [app/module3](app/module3), there are batch files that wrap the Docker commands:

- [app/module3/run-docker.bat](app/module3/run-docker.bat)
- [app/module3/stop-docker.bat](app/module3/stop-docker.bat)
- [app/module3/run-docker-prod.bat](app/module3/run-docker-prod.bat)
- [app/module3/stop-docker-prod.bat](app/module3/stop-docker-prod.bat)

These are useful for users who prefer double-clicking a script instead of typing commands.

## Login Accounts

The login page uses role-based accounts. The seeded demo credentials are:

- `homeowner` / `home123`
- `developer` / `dev123`
- `legal` / `legal123`
- `homeowner2` / `home223`
- `developer2` / `dev223`
- `legal2` / `legal223`
- `admin` / `admin123`

By default the app uses database-backed login accounts. A demo fallback mode exists for local testing only and should stay disabled in production.

## Main User Flow

1. Open the login page and sign in with the correct role.
2. The role dashboard appears.
3. Homeowner users save claim details such as state, court location, claim amount, transaction date, and item/service type.
4. Homeowner users can add remarks and upload evidence images for each defect.
5. Developer users can update defect status and completion dates.
6. Legal users can generate reports for tribunal review.
7. The app compiles case data, asks Groq for narrative text, and exports a PDF report.

## What the app stores

- PostgreSQL tables for users, defects, report profiles, and claim registry data.
- JSON files for remarks, status, completion dates, evidence metadata, and audit history inside [app/module3/data](app/module3/data) and [app/module3/audit_data](app/module3/audit_data).
- Uploaded images inside [app/module3/evidence](app/module3/evidence).

## Useful URLs

- Login page: `http://localhost:5000/login`
- Main dashboard after login: `http://localhost:5000/`

## Troubleshooting

If the app does not start, check these first:

1. PostgreSQL is running and the database name, user, and password are correct.
2. `GROQ_API_KEY` is set correctly in `.env`.
3. The database schema has been imported before first launch.
4. Port `5050` is not already being used by another process.
5. Docker Desktop is running if you are using Docker.

Helpful commands:

```powershell
docker compose logs --tail=100 app
Invoke-WebRequest http://localhost:5050/login -UseBasicParsing
docker compose down
docker compose build --no-cache
docker compose up -d
```

If the app throws a production secret error, set `FLASK_SECRET_KEY` to a strong value before starting in production mode.

## Notes for New Deployers

- Use the module3 folder for deployment, not the repository root.
- Keep `ENABLE_DEMO_LOGIN_FALLBACK=0` unless you are doing local demo testing.
- Set `SESSION_COOKIE_SECURE=1` only when the app is served over HTTPS.
- Use production compose with Gunicorn when you are deploying for real users.

Deployment commands (Windows PowerShell, Docker)

Prerequisites
Install Docker Desktop
Ensure PostgreSQL is running and reachable
Open PowerShell
Go to module3 directory
cd C:\Users\user\Automated-Compliance-Report-Generation\app\module3

Clear host DB env overrides (important)
Remove-Item Env:DB_HOST -ErrorAction SilentlyContinue
Remove-Item Env:DB_PORT -ErrorAction SilentlyContinue
Remove-Item Env:DB_NAME -ErrorAction SilentlyContinue
Remove-Item Env:DB_USER -ErrorAction SilentlyContinue
Remove-Item Env:DB_PASSWORD -ErrorAction SilentlyContinue

Create environment file
Copy-Item .env.example .env

Edit .env
notepad .env

Set these values in .env:

GROQ_API_KEY=your_real_key
DB_HOST=host.docker.internal
DB_PORT=5432
DB_NAME=compliance_db
DB_USER=postgres
DB_PASSWORD=your_db_password
APP_PORT=5050
Build and start (development)
docker compose up -d --build

Verify running
docker compose ps
docker compose logs --tail=100 app

Open app
http://localhost:5050/login

Stop app
docker compose down

Production-style commands (Gunicorn)

Go to module3
cd C:\Users\user\Automated-Compliance-Report-Generation\app\module3

Start production compose
docker compose -f docker-compose.prod.yml up -d --build

Check status/logs
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 app

Stop production
docker compose -f docker-compose.prod.yml down

Quick troubleshooting commands

Check app endpoint from host:
Invoke-WebRequest http://localhost:5050/login -UseBasicParsing

Follow live logs:
docker compose logs -f app

Rebuild from clean state:
docker compose down
docker compose build --no-cache
docker compose up -d

Demo accounts
homeowner / home123
developer / dev123
legal / legal123
homeowner2 / home223
developer2 / dev223
legal2 / legal223
admin / admin123
