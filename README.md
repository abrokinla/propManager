# PropManager

A SaaS platform for real estate agents to manage properties, units, tenants, payments, and maintenance requests.

## Architecture

| Layer | Stack | Hosting |
|---|---|---|
| **Backend** | Django 6.0, Django REST Framework, SimpleJWT | Render |
| **Frontend** | Next.js 15, React 19, TypeScript, Axios | Cloudflare Workers (OpenNext) |
| **Database** | PostgreSQL 16 | Supabase |
| **Auth** | JWT (access + refresh tokens) | — |

## Features

- **Properties** — CRUD with address, type, status, purchase/rental details
- **Units** — Per-property units with rent, deposit, bedroom/bathroom counts
- **Tenants** — Manage tenant profiles linked to units
- **Payments** — Track rent payments with amounts, dates, and methods
- **Maintenance** — Log and track maintenance requests per unit
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

| Endpoint | Method | Description |
|---|---|---|
| `/api/token/` | POST | Obtain access + refresh token |
| `/api/token/refresh/` | POST | Refresh access token |
| `/api/register/` | POST | Create user account |
| `/api/properties/` | GET/POST | List / create properties |
| `/api/properties/{id}/` | GET/PUT/PATCH/DELETE | Property detail |
| `/api/units/` | GET/POST | List / create units |
| `/api/units/{id}/` | GET/PUT/PATCH/DELETE | Unit detail |
| `/api/tenants/` | GET/POST | List / create tenants |
| `/api/tenants/{id}/` | GET/PUT/PATCH/DELETE | Tenant detail |
| `/api/payments/` | GET/POST | List / create payments |
| `/api/payments/{id}/` | GET/PUT/PATCH/DELETE | Payment detail |
| `/api/maintenance/` | GET/POST | List / create requests |
| `/api/maintenance/{id}/` | GET/PUT/PATCH/DELETE | Maintenance detail |
| `/api/health/` | GET | Health check |

### Query Parameters

All list endpoints support:

- `?search=` — Full-text search across relevant fields
- `?ordering=` — Sort by field (prefix `-` for descending)
- `?page=` — Page number (25 items per page)
- `?field=value` — Exact field filter (e.g. `?status=active`)

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key |
| `DEBUG` | No | `True` | Enable debug mode |
| `ALLOWED_HOSTS` | No | `localhost,127.0.0.1` | Comma-separated allowed hosts |
| `DATABASE_URL` | No | SQLite | PostgreSQL connection string |
| `CORS_ALLOWED_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `DJANGO_LOG_LEVEL` | No | `INFO` | Root logger level |

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

## Development

### Running Tests

```bash
python manage.py test
```

### Code Style

This project follows standard Django conventions. Run tests before pushing.

## License

MIT
