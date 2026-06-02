# CertifierBackEnd — Render Deployment

This repository contains a Django backend for certificate generation and verification. The repo has been prepared for deployment on Render.com.

## What I changed (non-functional)
- `Certifier_Project/settings.py` now reads production configuration from environment variables (SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASE_URL, etc.).
- WhiteNoise added for static file serving in production.
- `requirements.txt` added with required production dependencies.

## Render deployment steps
1. Create a new Web Service on Render using this GitHub repo.
   - Runtime: Python
   - Branch: `main`
   - Build Command:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

   - Start Command:

```bash
gunicorn Certifier_Project.wsgi:application --bind 0.0.0.0:$PORT
```

2. Add a Render Postgres database service and attach it to the Web Service. Render will provide a `DATABASE_URL` env var automatically.

3. Environment variables (required)
- `SECRET_KEY` — Django secret key (strong random string). Required for production.
- `DATABASE_URL` — Render Postgres connection string (set automatically when you attach the DB service).
- `GOOGLE_OAUTH_CLIENT_ID` — Google OAuth client ID (used for Google login).
- `GOOGLE_OAUTH_CLIENT_SECRET` — Google OAuth client secret.
- `GOOGLE_OAUTH_REDIRECT_URI` — e.g. `https://your-service.onrender.com/api/auth/google/callback/`
- `CERT_EDDSA_SIGNING_KEY` — Ed25519 signing key (hex). If omitted, the app will generate one at startup but it will not be persistent.

Recommended / optional env vars
- `DEBUG` — set to `False` in production. (`True` or `1` enables debug.)
- `ALLOWED_HOSTS` — comma-separated hostnames (e.g. `your-service.onrender.com`).
- `CORS_ALLOW_ALL_ORIGINS` — set to `False` in production. (`True` by default in dev.)
- `CSRF_TRUSTED_ORIGINS` — comma-separated trusted origins (e.g. `https://your-frontend.com`).
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` — fallback DB settings if `DATABASE_URL` is not used.
- `VERIFICATION_BASE_URL` — base URL used when `QR_ENCODE_MODE=verification_url` (e.g. `https://your-service.onrender.com`).
- `QR_ENCODE_MODE` — `certificate_id` (default) or `verification_url`.
- `FONT_DIR` — optional path to fonts used by PDF generation.

4. Persistent media
The app writes generated certificate PDFs and uploads to `MEDIA_ROOT` (defaults to `media/`). Render's filesystem is ephemeral. Use one of:
- Attach a Render Persistent Disk and set `MEDIA_ROOT` to the mounted path.
- Use an external object store (S3) and configure Django `DEFAULT_FILE_STORAGE` to use `django-storages` (not added by default).

5. Google OAuth configuration
- In Google Cloud Console, add the Redirect URI exactly as `GOOGLE_OAUTH_REDIRECT_URI` (e.g. `https://your-service.onrender.com/api/auth/google/callback/`).

6. Common commands (local)
```bash
# Create virtualenv
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Notes
- The code still supports local Postgres defaults when `DATABASE_URL` is not set to ease local development.
- Do **not** expose `CERT_EDDSA_SIGNING_KEY` or `SECRET_KEY` publicly.

If you want, I can also:
- Add a `Procfile` or `render.yaml` for automatic configuration.
- Configure `django-storages` + S3 for persistent media.
- Run a quick test deploy on your Render account if you provide access.
