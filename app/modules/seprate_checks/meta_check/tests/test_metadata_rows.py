from app.modules.seprate_checks.meta_check.metadata_rows import build_metadata_rows


def test_build_metadata_rows_matches_reference_fields_and_support_flags():
    rows = build_metadata_rows({
        "title": "Example title",
        "meta_description": "Example description",
        "page_metadata": {
            "keywords": "one, two",
            "author": "Example Author",
            "viewport": "width=device-width, initial-scale=1.0",
            "robots_meta": "index, follow",
            "theme_color": "#FF5722",
            "twitter": {
                "twitter:card": ["summary_large_image"],
                "twitter:title": ["Example title"],
                "twitter:description": ["Example description"],
                "twitter:image": ["https://example.com/image.png"],
            },
        },
    })

    by_tag = {row["tag"]: row for row in rows}
    assert set(by_tag) == {
        "title", "description", "keywords", "author", "viewport", "robots",
        "theme-color", "twitter:card", "twitter:title", "twitter:description",
        "twitter:image",
    }
    assert by_tag["keywords"]["content"] == "one, two"
    assert by_tag["keywords"]["google_supported"] is False
    assert by_tag["keywords"]["bing_supported"] is True
    assert by_tag["twitter:image"]["content"] == "https://example.com/image.png"