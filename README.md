# AI-Driven Inventory Optimization & Fulfillment Intelligence

Backend foundation built with Python 3.11, FastAPI, SQLAlchemy 2.0, SQLite, Alembic, Pydantic v2, Pytest, and Docker.

---

## Architecture Overview

This project uses a **Modular Monolith** pattern with strict separation of concerns:

- `app/api`: HTTP route handlers and API request/response validation.
- `app/core`: Application configuration, structured logging, database engines, and core utilities.
- `app/db`: Database models (`DeclarativeBase`) and session management.
- `app/schemas`: Pydantic data schemas for validation and serialization.
- `alembic`: Database migrations.
- `tests`: Deterministic unit and integration test suite.

---

## Local Development Setup

### 1. Environment Configuration

Copy `.env.example` to create your local `.env` configuration:

```bash
cp .env.example .env
```

### 2. Virtual Environment & Dependencies

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt -r requirements-dev.txt
```

### 3. Running Database Migrations

Apply Alembic migrations to set up your local SQLite database:

```bash
alembic upgrade head
```

### 4. Running the Development Server

Start the application with Uvicorn:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Access API Documentation:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health Endpoint: `http://127.0.0.1:8000/api/v1/health`

---

## Running with Docker Compose

To build and run the entire stack using Docker Compose:

```bash
docker-compose up --build
```

---

## Testing & Quality Assurance

Run the test suite:

```bash
pytest
```

Run code formatting and linting checks:

```bash
ruff check .
```
