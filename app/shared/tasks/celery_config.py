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
    "serp_rank_check.sweep_stuck_checks": {
        "queue": "serp_maintenance",
    },
    "audit.*": {
        "queue": "audit",
    },
    "streaming_audit.*": {
        "queue": "streaming_audit",
    },
    "core_seo.*": {
        "queue": "crawler",
    },
    "reports.*": {
        "queue": "email",
    },
}


