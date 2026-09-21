task_routes = {
    "auth.*": {
        "queue": "email",
    },
    "crawler.*": {
        "queue": "crawler",
    },
    "lighthouse.*": {
        "queue": "crawler",
    },
    "audit.*": {
        "queue": "audit",
    },
    "reports.*": {
        "queue": "email",
    },
}
