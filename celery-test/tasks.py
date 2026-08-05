from celery import Celery
import os

redis_host = os.getenv("REDIS_HOST", "127.0.0.1")

app = Celery(
    "tasks",
    broker=f"redis://{redis_host}:6379/0",
    backend=f"redis://{redis_host}:6379/0"
)

@app.task
def add(x, y):
    return x + y