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
    "sitemap.*": {
        "queue": "crawler",
    },
    "link_analysis.*": {
        "queue": "crawler",
    },
    "audit.*": {
        "queue": "audit",
    },
    "reports.*": {
        "queue": "email",
    },
}
