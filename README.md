# CertifierBackEnd — Certificate Generation & Verification

## 📝 Project Overview & Significance

The development of CertiFier provides significant benefits to the University of the Assumption by modernizing its administrative infrastructure and promoting environmental sustainability. By replacing traditional, resource-heavy paper processes with an automated web-based system, the institution can drastically reduce its carbon footprint and mitigate the greenhouse gas emissions associated with large-scale printing. This shift not only aligns the university with eco-friendly practices but also optimizes operational efficiency, allowing the College of Information Technology and Computer Learning Sciences faculty to bypass manual mailing and repetitive data entry through streamlined bulk generation and secure digital storage.

Furthermore, the study is highly significant for the students and the integrity of the academic credentials they receive. Through the integration of the EdDSA digital signature algorithm, the system establishes a robust security framework that ensures certificates are tamper-proof and easily verifiable, protecting the reputation of both the student and the university. Students gain the convenience of a centralized dashboard for instant access and verification of their credentials, while the institution benefits from a scalable, layered architecture that ensures data integrity. Ultimately, this research serves as a technological blueprint for other departments to transition into a more secure, efficient, and sustainable digital future.

## 🚀 Tech Stack

- **Backend:** [Django 5.2](https://www.djangoproject.com/) (Python)
- **API Framework:** [Django REST Framework](https://www.django-rest-framework.org/)
- **Database:** [PostgreSQL](https://www.postgresql.org/) (via Render Postgres)
- **File Storage:** [Supabase Storage](https://supabase.com/storage) (S3-Compatible) — Provides persistent storage for templates and certificates.
- **Deployment:** [Render](https://render.com/) (Web Service + Managed Postgres)
- **PDF Generation:** [ReportLab](https://www.reportlab.com/)
- **Security:** Ed25519 (EdDSA) Digital Signatures via [PyNaCl](https://pynacl.readthedocs.io/)
- **Authentication:** Google OAuth 2.0 & JWT (SimpleJWT)

## 🛠️ Features

- **Dynamic PDF Rendering:** Position text and QR codes on certificate templates via JSON-based markers.
- **S3-Compatible Persistence:** Integrated with Supabase Storage to ensure certificates and templates persist across server restarts (ideal for Render's Free Tier).
- **QR Code Verification:** Automatically generates QR codes for instant certificate validation.
- **Digital Signatures:** Every certificate is cryptographically signed to prevent tampering.

## 📦 Deployment on Render

### 1. Build & Start Commands
- **Build Command:**
  ```bash
  pip install -r requirements.txt
  python manage.py migrate
  python manage.py collectstatic --noinput
  ```
- **Start Command:**
  ```bash
  gunicorn Certifier_Project.wsgi:application --bind 0.0.0.0:$PORT
  ```

### 2. Environment Variables (Required)
| Variable | Description |
| :--- | :--- |
| `SECRET_KEY` | Django secret key for security. |
| `DATABASE_URL` | Render Postgres connection string (automatic). |
| `SUPABASE_STORAGE_ACCESS_KEY_ID` | Supabase S3 Access Key. |
| `SUPABASE_STORAGE_SECRET_ACCESS_KEY` | Supabase S3 Secret Key. |
| `SUPABASE_STORAGE_BUCKET_NAME` | Name of your Supabase bucket (e.g., `media`). |
| `SUPABASE_STORAGE_ENDPOINT_URL` | Supabase S3 Endpoint URL. |
| `GOOGLE_OAUTH_CLIENT_ID` | Google OAuth Client ID. |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google OAuth Client Secret. |

## 📂 Storage Configuration (Supabase)

To ensure files aren't lost when Render's ephemeral storage wipes:
1. Create a **Public** bucket in Supabase named `media`.
2. Go to **Project Settings > Storage** to find your **S3 Management** credentials.
3. Add the Access Key, Secret Key, and Endpoint to your Render environment variables.

## 💻 Local Development

```bash
# 1. Setup Virtual Environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# 2. Install Dependencies
pip install -r requirements.txt

# 3. Setup Environment
# Copy .env.template to .env and fill in values.
# If SUPABASE keys are missing, it defaults to local FileSystemStorage.

# 4. Run Server
python manage.py migrate
python manage.py runserver
```

## 📜 Digital Signatures
To generate a persistent signing key for your production environment:
```bash
python manage.py generate_signing_key
```
Copy the printed hex key into your `CERT_EDDSA_SIGNING_KEY` environment variable.
