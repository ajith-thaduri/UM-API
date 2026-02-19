# UM-API

Unified Medical API (UM-API) is a robust FastAPI-based backend designed for medical data processing, analysis, and management. It provides a comprehensive suite of endpoints for handling cases, clinical analysis, RAG (Retrieval-Augmented Generation) capabilities, and user management.

## 🚀 Key Features

- **Case Management**: Create, update, and manage medical cases and files.
- **Clinical Intelligence**: Advanced clinical agents for medical data extraction and analysis.
- **RAG Services**: Retrieval-Augmented Generation for intelligent querying of medical documents.
- **Analytics & Dashboards**: Comprehensive tracking of medical metrics and case progress.
- **Secure Authentication**: OAuth2 and JWT-based authentication system.
- **Wallet & Usage**: Integrated system for tracking usage and managing wallet balances.
- **Flexible Storage**: Support for both local and S3-compatible storage.

## 🛠 Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Vector Search**: pgvector for RAG capabilities
- **Task Queue**: Celery (optional/configurable)
- **Documentation**: Swagger UI (OpenAPI)

## 📋 API Endpoints

The API covers several domains:

- `/api/v1/auth`: Authentication and token management
- `/api/v1/cases`: Medical case and file management
- `/api/v1/clinical`: Clinical analysis and intelligence
- `/api/v1/rag`: Document retrieval and querying
- `/api/v1/analytics`: Dashboard and reporting data
- `/api/v1/users`: User profile and preference management
- `/api/v1/wallet`: Usage tracking and billing

## 🚦 Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL
- Virtual Environment (recommended)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ajith-thaduri/UM-API.git
   cd UM-API
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables in `.env`:
   ```env
   DATABASE_URL=postgresql://user:password@localhost/dbname
   SECRET_KEY=your-secret-key
   ```

4. Run the application:
   ```bash
   uvicorn app.main:app --reload
   ```

Access the interactive API documentation at `http://localhost:8000/docs`.

## 📄 License

Proprietary. All rights reserved.
