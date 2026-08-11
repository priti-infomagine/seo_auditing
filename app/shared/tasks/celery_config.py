task_routes = {
    "auth.*": {
        "queue": "otp",
    },
    "crawler.*": {
        "queue": "crawler",
    },
    "audit.*": {
        "queue": "audit",
    },
}
