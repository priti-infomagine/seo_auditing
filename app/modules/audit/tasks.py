from app.shared.tasks.celery_app import celery_app


@celery_app.task(name="audit.run_audit_job", queue="audit")
def run_audit_job(job_id: str) -> dict:
    raise NotImplementedError("Audit task integration pending.")
