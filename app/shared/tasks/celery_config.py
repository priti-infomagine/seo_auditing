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
    "serp_rank_check.run_serp_check": {
        "queue": "serp_io",
    },
    "serp_rank_check.build_preview": {
        "queue": "serp_preview",
    },
    "serp_rank_check.sweep_stuck_checks": {
        "queue": "serp_maintenance",
    },
    "serp_rank_check.refresh_reference_data": {
        "queue": "serp_maintenance",
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
