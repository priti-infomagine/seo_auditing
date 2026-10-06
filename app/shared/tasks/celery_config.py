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
    "redirect_check.*": {
        "queue": "crawler",
    },
    "audit.*": {
        "queue": "audit",
    },
    "streaming_audit.*": {
        "queue": "streaming_audit",
    },
    "reports.*": {
        "queue": "email",
    },
}
