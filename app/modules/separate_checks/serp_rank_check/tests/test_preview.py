from app.modules.seprate_checks.serp_rank_check.preview import (
    render_preview_html,
)


def test_preview_contains_only_entered_domain_results():
    html = render_preview_html(
        keyword="seo tools",
        target_domain="example.com",
        device="desktop",
        result={
            "found": True,
            "best_position": 2,
            "top_results": [
                {
                    "position": 1,
                    "domain": "other.com",
                    "url": "https://other.com/",
                    "title": "Other result",
                    "snippet": "Other snippet",
                },
                {
                    "position": 2,
                    "domain": "example.com",
                    "url": "https://example.com/page",
                    "title": "Entered domain result",
                    "snippet": "Entered domain snippet",
                },
            ],
        },
    )

    assert "Entered domain result" in html
    assert "Entered domain snippet" in html
    assert "Other result" not in html
    assert "Other snippet" not in html