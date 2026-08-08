from app.shared.tasks.celery_app import celery_app
from app.modules.auth import tasks as auth_tasks
from app.modules.crawler import tasks as crawler_tasks
from app.modules.audit import tasks as audit_tasks

celery = celery_app
