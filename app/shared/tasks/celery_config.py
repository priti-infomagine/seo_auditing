task_routes = {
    "auth.*": {
        "queue": "email",
    },
    "crawler.*": {
        "queue": "crawler",
    },
    "audit.*": {
        "queue": "audit",
    },
}
