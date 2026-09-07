from celery import Celery

from app.core.config import settings

broker_url = str(settings.REDIS_BROKER_URL)
backend_url = str(settings.REDIS_BACKEND_URL)

celery_app = Celery(
    "seo_tool",
    broker=broker_url,
    backend=backend_url,
    include=[
        "app.modules.auth.tasks",
        "app.modules.crawler.tasks",
        "app.modules.audit.tasks",
    ],
)

celery_app.config_from_object("app.shared.tasks.celery_config")

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=60,
    task_acks_on_failure=False,
    # Limit how long a broker operation can block — prevents indefinite
    # hangs when the Redis connection is slow or unresponsive.
    redis_socket_timeout=10,
    redis_socket_connect_timeout=5,
    broker_transport_options={
        "socket_timeout": 10,
        "socket_connect_timeout": 5,
    },
)

celery_app.conf.beat_schedule = {
    "cleanup-expired-otps-every-day": {
        "task": "auth.cleanup_expired_otps",
        "schedule": 86400.0,
    },
    "cleanup-expired-blacklisted-tokens-every-day": {
        "task": "auth.cleanup_expired_blacklisted_tokens",
        "schedule": 86400.0,
    },
    "cleanup-expired-refresh-tokens-every-day": {
        "task": "auth.cleanup_expired_refresh_tokens",
        "schedule": 86400.0,
    },
}
