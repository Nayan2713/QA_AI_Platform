# 🛠️ QA Engineer MVP - Tech Stack & Architecture Rationale

This document serves as the developer registry for all technologies, frameworks, and packages used in the **QA Engineer MVP** platform. It details **what** is used, **why** we use it (the design rationale), and acts as a living document to track additions as the codebase evolves.

---

## 🗃️ Technology Registry

### 1. Backend Core (Python & Django)

| Technology / Library | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **Python 3.10+** | The programming language for our backend. Chosen for its rich ecosystem in automation (Playwright), AI integrations (Ollama/requests), and web frameworks. | `Active` |
| **Django 4.2** | A robust, highly secure, batteries-included web framework. Provides an out-of-the-box database ORM, user auth systems, and security middleware. | `Active` |
| **Django REST Framework (DRF)** | Extends Django to expose clean, structured REST API endpoints for our React client. | `Active` |
| **djangorestframework-simplejwt** | Implements secure, stateless JSON Web Token (JWT) user authentication (Login/Register). Prevents session-state leaks. | `Active` |
| **PostgreSQL** | A powerful, open-source object-relational database system. Used as the main database for storing application configurations, discovered pages, test cases, and execution logs securely and efficiently. | `Active` |

---

### 2. Task Queue & Background Processors

| Technology / Library | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **Celery 5.3** | Task worker manager. Browser crawling and test executions can take minutes; Celery runs them asynchronously in background threads so HTTP request threads never timeout or freeze. | `Active` |
| **Redis 7** | A high-performance in-memory key-value database. Used as Celery's message broker to queue tasks and store execution results. | `Active` |
| **django-celery-results** | Integrates Celery task result storage directly into our Django database, letting us query task states via standard DRF serializing viewsets. | `Active` |

---

### 3. Browser Automation & Crawler

| Technology / Library | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **Playwright for Python** | Modern browser automation engine. Chosen over Selenium because it supports headless execution out-of-the-box, has faster start times, captures screenshots natively, and provides robust auto-waiting on element selectors. | `Active` |

---

### 4. Local AI Engine

| Technology / Library | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **Ollama** | Self-hosted LLM engine wrapper. Runs models like `qwen:7b` locally, keeping the application entirely free of third-party API keys (like OpenAI), reducing run costs to zero, and preserving data privacy. | `Active` |

---

### 5. Frontend Client (React & Vite)

| Technology / Library | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **React 18** | A component-based frontend library. Enables building reusable UI items (buttons, timeline logs, bug grids) with reactive states (`useState`). | `Active` |
| **TypeScript** | Adds strong type checkings, autocomplete features, and contracts between Django JSON responses and our frontend component props. | `Active` |
| **Vite 4** | Next-generation frontend tooling. Replaces heavy Webpack configurations with instant Hot Module Replacement (HMR) and fast build compilations. | `Active` |
| **Axios** | HTTP request client. Features global request interceptors that automatically read our simple-jwt tokens from `localStorage` and inject them as headers. | `Active` |

---

### 6. Design & Styling (Custom CSS)

| Styling Component | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **Glassmorphic Layouts** | Translucent overlays (`backdrop-filter: blur(16px)`), thin glowing borders, and dark backgrounds. Gives a premium dark-mode developer-tool aesthetic. | `Active` |
| **Severity Indicators** | Highly visible badge systems (Critical: Neon Red, High: Orange, Medium: Blue, Low: Green) for rapid visual analysis. | `Active` |
| **Vibrant Micro-animations** | Hover transitions on card configurations, spinning loaders, and slide-in drawers to keep the workspace feeling alive and interactive. | `Active` |

---

### 7. Infrastructure & Deployment

| Tool / Config | Purpose (Why we use it) | Status |
| :--- | :--- | :--- |
| **Docker & Docker Compose** | Wraps the entire application stack. Allows starting Redis, Django, and Vite simultaneously in a single command (`docker-compose up --build`). | `Active` |
| **python-dotenv** | Loads local variables (secret keys, API ports) from a `.env` file into python's environment, decoupling code from secret settings. | `Active` |

---

## ⏳ Evolution Log (Changelog)

This table logs changes, updates, or packages added to the platform over time, explaining why they were introduced.

| Date | Package / Rationale | Target Module | Author |
| :--- | :--- | :--- | :--- |
| **2026-06-20** | **`django-cors-headers`** Added to allow cross-origin requests from our React front-end (port 3000) to our Django API (port 8000). | Module 1 (Backend Setup) | Antigravity |
| **2026-06-20** | **`django-celery-results`** Added to write Celery task execution results directly into the database. | Module 1 (Backend Setup) | Antigravity |
| **2026-06-20** | **Redis Protocol Monkeypatch** Added to force the Redis driver to use RESP2. Prevents crashes (`unknown command HELLO`) caused by older Redis servers. | Module 11 (Integration) | Antigravity |
| **2026-06-20** | **Celery Explicit Imports** Added task paths to `app.conf.imports` inside `celery.py` to solve the silent worker boot task-unregistered error. | Module 11 (Integration) | Antigravity |
