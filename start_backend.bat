@echo off
echo Starting Brightcone UM Shield Backend...
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Check if .env exists
if not exist .env (
    echo WARNING: .env file not found!
    echo Please create .env file with OPENAI_API_KEY
    echo.
)

REM Run database migrations
echo Running database migrations...
python -m alembic upgrade head
echo.

REM Start the server
echo Starting FastAPI server...
echo Server will be available at http://localhost:8000
echo API docs: http://localhost:8000/api/docs
echo.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause






