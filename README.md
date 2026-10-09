# AutoHeal AI

AutoHeal AI is a FastAPI/PostgreSQL backend with a React dashboard for incident diagnosis, source-error ingestion, human repair approval, and safe recovery workflows.

## Windows PowerShell setup

From the repository root:

```powershell
Set-Location "C:\Users\mones\OneDrive\Desktop\AutoHeal"
.\auto\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements.txt
```

Create or update the root `.env` file. Never commit it:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set `GROQ_API_KEY` to your existing key and set `DATABASE_URL` to the PostgreSQL database you intend to use. The default template targets a local database named `autoheal`:

```dotenv
GROQ_API_KEY=your-key-here
GROQ_MODEL=llama-3.3-70b-versatile
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/autoheal
```

The backend loads `.env` from the repository root. The API key is never returned by an endpoint or logged by the settings loader.

## PostgreSQL initialization

Start PostgreSQL and create the database only if it does not already exist. This command does not drop or reset data:

```powershell
Get-Service postgresql* | Select-Object Name, Status
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres autoheal
```

If the database already exists, `createdb` reports that fact; do not use a drop or reset command. Verify connectivity through the backend:

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m app.init_db
```

`app.init_db` uses SQLAlchemy `create_all`, which creates missing tables and preserves existing tables and rows. Schema evolution should use Alembic migrations once the model stabilizes.

## Run the backend

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m uvicorn app.main:app --reload --app-dir .\backend
```

Check the endpoints:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/health/ready
Invoke-RestMethod http://127.0.0.1:8000/api/incidents
```

The recovery API is intentionally explicit:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/incidents/1/recover
Invoke-RestMethod http://127.0.0.1:8000/api/escalations
```

## Authentication and source-repair demo

Set a one-time setup token and a signing secret in the root `.env` before starting the backend:

```dotenv
AUTOHEAL_SETUP_TOKEN=generate-a-long-random-one-time-value
AUTOHEAL_AUTH_SECRET=generate-a-different-long-random-signing-secret
AUTOHEAL_APPROVED_WORKSPACE=C:\Users\mones\OneDrive\Desktop\AutoHeal\sample_app
AUTOHEAL_ADMIN_EMAIL=admin@gmail.com
AUTOHEAL_ADMIN_PASSWORD=admin@123
AUTOHEAL_ADMIN_DISPLAY_NAME=Aarthi GD
AUTOHEAL_ADMIN_ROLE=admin
AUTOHEAL_APPROVAL_EMAIL=aarthi@gmail.com
```

Repair approvals are always persisted in the dashboard. Without SMTP configuration,
the UI accurately labels them `Approval request created in AutoHeal` and does not
claim that an email was sent. Optional delivery can be enabled with these
server-only variables; never commit their values:

```dotenv
AUTOHEAL_SMTP_HOST=
AUTOHEAL_SMTP_PORT=587
AUTOHEAL_SMTP_USERNAME=
AUTOHEAL_SMTP_PASSWORD=
AUTOHEAL_SMTP_FROM=
```

When all SMTP values are configured and delivery is confirmed, the approval record
is labeled `Email sent and confirmed`. If delivery fails, the dashboard request
remains available and is labeled accordingly.

Run the non-destructive initializer after PostgreSQL is available:

```powershell
$env:PYTHONPATH = (Resolve-Path .\backend).Path
.\auto\Scripts\python.exe -m app.init_db
```

This creates the configured demo admin only when `admin@gmail.com` does not already exist. If it exists, initialization preserves its password and existing records while ensuring its configured display name and administrator role. To change the demo password before deploying outside local development, change `AUTOHEAL_ADMIN_PASSWORD` in `.env` and use a controlled password-rotation process; initialization intentionally does not overwrite an existing password.

Default local login:

```text
Email / User ID: admin@gmail.com
Password: admin@123
Display name: Aarthi GD
Role: admin
```

The password is configurable and is never returned by an API or included in frontend source. For additional non-admin local users, use the setup endpoint. Its setup token is never sent to the frontend:

```powershell
$body = @{
  username = "aarthi"
  full_name = "Aarthi G D"
  password = Read-Host "Password" -AsSecureString
  setup_token = Read-Host "Setup token" -AsSecureString
}
# Convert the two secure strings only for this local request; do not commit them.
$body.password = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($body.password))
$body.setup_token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($body.setup_token))
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/setup -ContentType "application/json" -Body ($body | ConvertTo-Json)
```

Log in from the frontend at `http://127.0.0.1:5173`. The browser stores only the short-lived signed bearer token. Groq credentials remain backend-only.

To demonstrate a real source error after logging in, copy the bearer token from the browser's authenticated request and run:

```powershell
Set-Location "C:\Users\mones\OneDrive\Desktop\AutoHeal\sample_app"
python .\run_error_report.py
```

The backend creates a persisted incident and pending approval. Approval applies only the reviewed calculator patch, runs the sample regression tests, and records the outcome. Rejection preserves the original source.

## GitHub repository links

Administrators can associate an HTTPS public GitHub repository URL with a registered
project from the Projects page. The backend-only endpoints are:

```text
GET    /api/projects
PUT    /api/projects/{project_id}/github
DELETE /api/projects/{project_id}/github
```

The update and delete operations require an administrator bearer token. Accepted URLs
must have the form `https://github.com/owner/repository` without credentials, query
strings, fragments, or extra path segments. The link is stored in PostgreSQL and is
returned on project reads. This feature does not clone repositories, access private
repository contents, store GitHub tokens, or modify source code.

## Run the frontend

In a second PowerShell window:

```powershell
Set-Location "C:\Users\mones\OneDrive\Desktop\AutoHeal\frontend"
Copy-Item .env.example .env -ErrorAction SilentlyContinue
npm install
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`. The frontend reads only `VITE_API_BASE_URL`; database credentials and `GROQ_API_KEY` remain backend-only.

Only allowlisted sandbox actions can execute automatically. Unknown, low-confidence, unsafe, or repeatedly failing repairs are stored in the in-app escalation queue. No external notification is claimed or attempted.

## Tests

Tests use an isolated in-memory SQLite database and never write to the configured PostgreSQL database:

```powershell
python -m pytest .\backend\tests -q
```

## Troubleshooting

- **`GROQ_API_KEY must not be empty`**: set `GROQ_API_KEY` in the root `.env`, not in frontend files.
- **Readiness returns 503**: confirm the PostgreSQL Windows service is running, the host/port/database in `DATABASE_URL` are correct, and the credentials have access.
- **`database "autoheal" does not exist`**: create it with `createdb.exe -U postgres autoheal`, after confirming that the configured PostgreSQL instance is the intended one.
- **`password authentication failed`**: update only the password portion of `DATABASE_URL`; do not paste credentials into source files or commit `.env`.
- **`ModuleNotFoundError`**: activate the project environment and rerun `python -m pip install -r .\backend\requirements.txt`.
