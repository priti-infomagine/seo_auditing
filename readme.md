Using Docker Compose (recommended)

docker-compose up --build
This starts Redis, web server (uvicorn), Celery worker, Celery beat, and Minio together.

Start components separately (local development)

# Terminal 1: Redis
redis-server

# Terminal 2: Uvicorn server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 3: Celery worker
celery -A app.shared.tasks worker --loglevel=info

# Terminal 4: Celery beat scheduler
celery -A app.shared.tasks beat --loglevel=info
Verify it's running

API: http://localhost:8000/docs
Test Celery: POST /api/v1/celery/test-celery
Redis: redis-cli ping → should return PONG
Note: If you get RuntimeError: Task got Future