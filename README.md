# ⚡ QA Engineer MVP Platform

QA Engineer MVP is an intelligent, self-hosted autonomous Quality Assurance platform. Developers can input any target website URL, and the platform automatically discovers its pages and forms, generates AI-driven test suites (using a local Ollama server, or robust deterministic templates if offline), executes the test steps inside automated browser instances (via Playwright), classifies step errors into severe bugs, and streams results in real-time to a premium dark-mode React dashboard.

---

## 🏗️ Architecture Overview

The application is split into a decoupled Backend API + Celery Worker architecture, and a Single Page Application (SPA) frontend.

```mermaid
graph TD
    Client[React Frontend - Port 3000] -->|HTTP / JWT| API[Django REST API - Port 8000]
    API -->|Read/Write| DB[(SQLite Database)]
    API -->|Queue Tasks| Redis[(Redis Broker)]
    Redis -->|Poll Tasks| Celery[Celery Worker]
    
    subgraph Celery Tasks
        Celery -->|1. Probe Status| MCP[MCP Server - Port 5001]
        Celery -->|2. Web Crawler| PW_Craw[Playwright Crawler]
        Celery -->|3. Generate Tests| LLM[Ollama Local LLM - Port 11434]
        Celery -->|4. Run Test Suite| PW_Exec[Playwright Executor]
        Celery -->|5. Analyze Failures| Bug_Det[Bug Classifier]
    end
    
    PW_Craw -->|Saves Pages| DB
    LLM -->|Saves TestCases| DB
    PW_Exec -->|Saves Step Logs & base64 Screenshots| DB
    Bug_Det -->|Saves Bugs| DB
```

---

## 🗄️ Database Schema Diagram

The database uses a clean, relational SQLite layout optimized for MVP:

- **Users**: Standard Django authentication table (`auth_user`).
- **Applications**: Registered testing sites. Stores target URLs, status, and optional login credentials.
- **Pages**: Extracted subpages. Stores URLs, titles, detected `<form>` configurations, and `<button>` selectors in JSON fields.
- **TestCases**: AI or template-driven test scenarios. Stores JSON action arrays representing execution steps.
- **TestRuns**: Instances of test suite runs. Tracks execution state (COMPLETED, FAILED, RUNNING) and bug counts.
- **TestResults**: Step-by-step logs for a `TestRun`. Stores pass/fail flags, error traces, and Base64 screenshot strings.
- **Bugs**: Defect tickets. Stores error summaries and classified severity rankings.

---

## 🚀 Getting Started (Installation & Running)

You can run the application either **locally on your machine** (optimal for debugging) or via **Docker Compose** (one-click deployment).

### Option A: Running Locally (Recommended for Development)

#### Prerequisites
- **Python**: version 3.10+
- **Node.js**: version 18+
- **Redis**: running on `localhost:6379`
- **Ollama (Optional)**: running locally with `ollama run qwen:7b` (or `mistral:7b`)

#### Setup Steps

1. **Clone & Environment Setup**:
   Create a `.env` file in the root directory (based on `.env.example`):
   ```bash
   cp .env.example .env
   ```

2. **Backend Setup**:
   Open a new terminal window:
   ```bash
   cd backend
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Mac/Linux:
   source venv/bin/activate
   
   pip install -r requirements.txt
   playwright install chromium
   
   python manage.py migrate
   python manage.py runserver
   ```
   The API will now be active at `http://localhost:8000`.

3. **Celery Worker Setup**:
   Open a new terminal window:
   ```bash
   cd backend
   # Activate your virtual environment
   .\venv\Scripts\activate


#run the celery
celery -A qa_engine worker -l info
celery -A qa_engine worker -l info -P solo
celery -A qa_engine worker -l info -P threads --concurrency=8

celery -A qa_engine worker -l info -P threads --concurrency=6 -Q discovery,execution,quality,celery


#stop the celery 

celery -A qa_engine purge -f

python manage.py shell -c "import django; django.setup(); from django.conf import settings; import redis; r = redis.Redis.from_url(settings.CELERY_BROKER_URL); print('Flushed Redis:', r.flushdb())"


   ```

4. **Frontend Setup**:
   Open a new terminal window:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open `http://localhost:3000` in your web browser.

---

### Option B: Running with Docker (Recommended for Production & Unified Dev)

This project provides a complete, production-ready multi-container Docker environment. We support two separate configurations depending on your requirements: **Development Mode** (with hot-reloading and debug ports) and **Production Mode** (with Gunicorn, Nginx reverse proxy, and resource constraints).

#### 1. Prerequisites
- **Docker** and **Docker Compose** installed (Docker Desktop for Windows/macOS).
- Local **Ollama** running on your host (if using AI test generation) and configured to accept external connections:
  - **macOS/Linux**: `OLLAMA_HOST=0.0.0.0 ollama serve`
  - **Windows**: Add an Environment Variable `OLLAMA_HOST` set to `0.0.0.0`, restart Ollama, and restart your terminal.

---

#### 2. Configuration Setup
1. Copy `.env.example` from the root directory to `.env` in the root:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and fill in the required variables (e.g. `SECRET_KEY`, `OPENAI_API_KEY` if using OpenAI, etc.). The defaults are pre-configured to work with the Docker Compose service names out-of-the-box.

---

#### 3. Development Mode (with Hot Reloading)
This setup mounts the source directories (`./backend` and `./frontend`) into the containers, enabling live backend reload and frontend Vite hot module replacement (HMR).

- **Build and Start**:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
  ```
- **Accessing the Application**:
  - Main Gateway (Nginx Proxy): [http://localhost](http://localhost) (Proxies `/` to Vite dev server and `/api` to Django)
  - Direct Frontend (Vite): [http://localhost:3000](http://localhost:3000)
  - Direct Backend API (Django): [http://localhost:8000/admin/](http://localhost:8000/admin/)
  - Database (Postgres): `localhost:5432`
  - Cache/Broker (Redis): `localhost:6379`

---

#### 4. Production Mode (Optimized & Secure)
This setup compiles the React frontend to highly optimized static assets served directly by Nginx. The Django API runs under Gunicorn (4 workers, 2 threads) with strict resource limits and no developer ports exposed to the host OS.

- **Build and Start**:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
  ```
- **Accessing the Application**:
  - The application is exposed exclusively on Port 80: [http://localhost](http://localhost)
  - Admin Panel: [http://localhost/admin/](http://localhost/admin/)
  - API Health Check: [http://localhost/api/health/](http://localhost/api/health/)

---

#### 5. Database Migrations & Administration
- **Run migrations manually** (although they run automatically on backend web startup):
  ```bash
  docker compose exec backend python manage.py migrate
  ```
- **Create a Django Superuser**:
  ```bash
  docker compose exec -it backend python manage.py createsuperuser
  ```

---

#### 6. Monitoring & Logging
- **View logs for all services**:
  ```bash
  docker compose logs -f
  ```
- **View logs for a specific service (e.g. celery worker or backend)**:
  ```bash
  docker compose logs -f celery_worker
  docker compose logs -f backend
  ```

---

#### 7. Service Management
- **Stop all services**:
  ```bash
  docker compose down
  ```
- **Stop and remove all volumes (WARNING: deletes DB and Redis data)**:
  ```bash
  docker compose down -v
  ```
- **Restart a single service (e.g. restart the celery worker after a task edit)**:
  ```bash
  docker compose restart celery_worker
  ```

---

#### 8. Running Playwright & Celery Tasks
- Playwright is fully installed with all required Linux libraries and headless Chromium in the backend container.
- When you click "Execute" or "Discover" on the React dashboard, Celery sends the task to the Redis broker, and the `celery_worker` container launches a headless chromium browser instance to run the QA flows.
- **Run tests manually inside the container**:
  ```bash
  docker compose exec backend pytest
  ```

---

#### 9. Database Backup & Restore
- **Backup database**:
  ```bash
  docker compose exec -t postgres pg_dumpall -c -U postgres > backup.sql
  ```
- **Restore database**:
  ```bash
  cat backup.sql | docker compose exec -T postgres psql -U postgres
  ```

---

#### 10. Common Docker Troubleshooting
- **Playwright Chromium installation check**:
  ```bash
  docker compose exec backend python -m playwright install --with-deps chromium
  ```
- **Pruning dangling images/caches** (if builds fail due to disk space):
  ```bash
  docker system prune -a --volumes
  ```

---

## 📡 API Endpoint Documentation

### Authentication
* **POST** `/api/auth/register/` - Create a user profile. Returns token credentials.
* **POST** `/api/auth/login/` - Validate credentials. Returns JWT access/refresh tokens.

### Applications
* **GET** `/api/applications/` - List all registered applications.
* **POST** `/api/applications/` - Register a new application URL.
* **GET** `/api/applications/{id}/` - Retrieve details of a registered application.
* **POST** `/api/applications/{id}/discover/` - Trigger the page/form discovery worker.
* **GET** `/api/applications/{id}/pages/` - Retrieve all discovered subpages and structural elements.
* **GET** `/api/applications/{id}/status/` - Retrieve live crawling status.

### Test Cases
* **GET** `/api/test-cases/` - List all test cases.
* **POST** `/api/test-cases/generate/` - Request AI generation for `app_id`.
* **GET** `/api/test-cases/{id}/` - Retrieve steps for a test case.

### Test Runs (Execution)
* **GET** `/api/test-runs/` - List execution histories.
* **POST** `/api/test-runs/execute/` - Execute browser automation for `test_case_id`.
* **GET** `/api/test-runs/{id}/` - Fetch step logs and screenshot data.
* **GET** `/api/test-runs/{id}/status/` - Retrieve live runner completion metrics.

### Bug Tracking
* **GET** `/api/bugs/` - List all logged bugs.
* **GET** `/api/bugs/{id}/` - Retrieve bug reproduction description and severity.

---

## 🛠️ Troubleshooting Guide

### 1. Celery Tasks Stalled in "PENDING"
* **Cause**: The Celery worker is not running, or Redis is offline.
* **Fix**: Ensure Redis is running on port 6379 (`redis-cli ping` should return `PONG`). Start the worker using `celery -A qa_engine worker -l info` and verify it joins successfully.

### 2. Playwright Crashes on Docker Compose
* **Cause**: Container OS lacks libraries required to execute chromium headless.
* **Fix**: The provided `./backend/Dockerfile` runs `playwright install-deps chromium` during build. Rebuild the container using `docker-compose build --no-cache` to ensure all OS-level packages are populated.

### 3. No Test Cases Generated (Empty Test Suite)
* **Cause**: Ollama is not active or hasn't loaded the requested model.
* **Fix**: Check if Ollama is running (`curl http://localhost:11434`). The system has a built-in safety net: if Ollama is unreachable, it automatically triggers a **Deterministic Fallback Suite** generating form submissions and page checkups, so the testing pipeline remains active.

### 4. Playwright Timeout Failures
* **Cause**: The target website loads slow, or elements are rendering via dynamic JS animations past the 5-second action threshold.
* **Fix**: Adjust default step timeout thresholds in `backend/tasks/execution.py` or add a `wait` step (duration in milliseconds) inside your test case sequence.
