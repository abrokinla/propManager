# PropManager

A SaaS platform for real estate agents to manage properties, units, tenants, payments, and maintenance requests.

## Architecture

| Layer | Stack | Hosting |
|---|---|---|
| **Backend** | Django 6.0, Django REST Framework, SimpleJWT | Render |
| **Frontend** | Next.js 15, React 19, TypeScript, Axios | Cloudflare Workers (OpenNext) |
| **Database** | PostgreSQL 16 | Supabase |
| **Auth** | JWT (access + refresh tokens) | — |
| **File Storage** | Cloudinary | — |
| **Email** | SendGrid | — |
| **PDF** | ReportLab | — |

## Features

- **Properties** — CRUD with address, type, status, purchase/rental details
- **Units** — Per-property units with rent, deposit, bedroom/bathroom counts, occupancy tracking
- **Tenants** — Manage tenant profiles with document workflow (pending → sent → signed → active)
- **Payments** — Track rent payments with period coverage and multi-year support
- **Maintenance** — Log and track maintenance requests per unit with priority levels
- **Documents** — Generate tenancy agreement PDFs, send via email, collect signed copies via public upload link
- **Quit Notices** — Issue formal quit notices with auto-generated PDFs and email delivery
- **Reminders** — Send lease expiry, rent due, and document signing reminders via email; scheduled via management command
- **Dashboard** — Overview stats with revenue, occupancy rate, upcoming expirations, and recent payments
- **Pagination & Filtering** — Page-based pagination (25/page), search, ordering, and field filters on all list endpoints
- **JWT Authentication** — Access tokens (24h) + refresh tokens (7d) with rotation and blacklisting
- **Health Check** — `GET /api/health/` endpoint for monitoring

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (optional, for local PostgreSQL)

### Backend Setup

```bash
# Clone and enter the backend
git clone https://github.com/abrokinla/propManager.git
cd propmanager

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run migrations
python manage.py migrate

# Seed sample data (optional)
python manage.py loaddata properties/fixtures/sample.json

# Start dev server
python manage.py runserver
```

The API is now available at `http://localhost:8000/api/`.

### Frontend Setup

```bash
# Clone the frontend repo
git clone https://github.com/abrokinla/PropManager-frontend.git
cd PropManager-frontend/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

The app is now available at `http://localhost:3000`.

### Local PostgreSQL (Docker)

```bash
docker compose up -d
# DATABASE_URL=postgresql://propmanager:propmanager@localhost:5432/propmanager
```

## API

All endpoints require JWT authentication unless noted.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register/` | Create user account |
| POST | `/api/login/` | Login, returns access + refresh tokens |
| POST | `/api/token/refresh/` | Refresh access token |
| GET/PUT | `/api/profile/` | Get / update current user profile |

### Core CRUD

| Method | Endpoint | Description |
|---|---|---|
| GET/POST | `/api/properties/` | List / create properties |
| GET/PUT/PATCH/DELETE | `/api/properties/{id}/` | Property detail |
| GET/POST | `/api/units/` | List / create units |
| GET/PUT/PATCH/DELETE | `/api/units/{id}/` | Unit detail |
| GET/POST | `/api/tenants/` | List / create tenants |
| GET/PUT/PATCH/DELETE | `/api/tenants/{id}/` | Tenant detail |
| GET/POST | `/api/payments/` | List / create payments |
| GET/PUT/PATCH/DELETE | `/api/payments/{id}/` | Payment detail |
| GET/POST | `/api/maintenance/` | List / create requests |
| GET/PUT/PATCH/DELETE | `/api/maintenance/{id}/` | Maintenance detail |

### Documents

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tenants/{id}/documents/` | List tenant's documents |
| POST | `/api/tenants/{id}/send-document/` | Generate PDF, email tenant with upload link |
| POST | `/api/tenants/{id}/documents/{doc_id}/upload-signed/` | Upload signed PDF (multipart) |

### Public (no auth required)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/public/document/{token}/` | Fetch document data by signed token |
| POST | `/api/public/document/{token}/sign/` | Upload signed PDF (multipart) |

The `token` is a UUID generated when `send-document` is called. The tenant receives an email with a link like `https://frontend.com/upload-document/{token}`.

### Quit Notices

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/tenants/{id}/quit-notice/` | Issue quit notice (generates PDF, emails tenant) |
| GET | `/api/tenants/{id}/quit-notices/` | List quit notices for tenant |

### Reminders

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/tenants/{id}/send-reminder/` | Send reminder (`reminder_type`: `lease_expiry`, `rent_due`, `document_sign`) |
| GET | `/api/tenants/{id}/reminders/` | List sent reminders |

### Dashboard

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/dashboard/stats/` | Aggregated stats (properties, units, revenue, expirations, payments) |

### Other

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health/` | Health check (no auth) |

### Query Parameters

All list endpoints support:

- `?search=` — Full-text search across relevant fields
- `?ordering=` — Sort by field (prefix `-` for descending)
- `?page=` — Page number (25 items per page)
- `?field=value` — Exact field filter (e.g. `?status=active`)

## Environment Variables

### Required

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `SENDGRID_API_KEY` | SendGrid API key for email |

### Optional

| Variable | Default | Description |
|---|---|---|
| `DEBUG` | `True` | Enable debug mode |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DATABASE_URL` | SQLite | PostgreSQL connection string for production |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `DJANGO_LOG_LEVEL` | `INFO` | Root logger level |
| `DEFAULT_FROM_EMAIL` | `noreply@propmanager.com` | Sender email address |

## Scheduled Reminders

Run the following command daily (e.g. via cron-job.org hitting a Render cron URL or manually via SSH):

```bash
python manage.py send_reminders
```

This sends lease expiry reminders at 30, 14, 7, and 0 days before expiry.

## Deployment

### Backend (Render)

1. Push to GitHub
2. In Render Dashboard, create a **Web Service** connected to the repo
3. Set **Build Command**:
   ```
   pip install -r requirements.txt && python manage.py collectstatic --noinput
   ```
4. Set **Start Command**:
   ```
   python manage.py migrate && gunicorn propmanager.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
   ```
5. Add environment variables (see table above)
6. Deploy

### Frontend (Cloudflare Workers)

```bash
npm run cf-build
npm run deploy
```

Set `NEXT_PUBLIC_API_URL` as a Cloudflare secret pointing to the backend URL.

### Reminder Scheduling

Schedule a cron job (e.g., cron-job.org) to hit a command execution endpoint daily, or run:

```bash
python manage.py send_reminders
```

## Development

### Running Tests

```bash
python manage.py test
```

### Code Style

This project follows standard Django conventions. Run tests before pushing.

## License

MIT
