task_routes = {
    "app.modules.auth.tasks.*": {
        "queue": "otp",
    },
    "app.modules.crawler.tasks.*": {
        "queue": "crawler",
    },
    "app.modules.audit.tasks.*": {
        "queue": "audit",
    },
}
