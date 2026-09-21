# Crawler End-to-End Test Harness

## Overview

This test harness exercises the **complete crawler pipeline** against a diverse set of real public URLs. It documents exactly which layer made which decision at every step.

## Test Files

| File | Purpose |
|------|---------|
| `test_cases.py` | URL test matrix (15 diverse URLs) |
| `test_full_crawler.py` | Main test runner + pipeline logger |
| `results/` | Generated output per domain |

## Running the Tests

### As pytest (recommended)

```powershell
.\.venv\Scripts\python.exe -m pytest app/modules/crawler/tests/integration/test_full_crawler.py -v -s
```

### Standalone

```powershell
.\.venv\Scripts\python.exe app/modules/crawler/tests/integration/test_full_crawler.py
```

## URL Test Matrix

| # | URL | Category | Expected Behavior |
|---|-----|----------|-------------------|
| 1 | https://cyfuture.com | business_website | Normal HTTP/SSR, SEO extraction |
| 2 | https://www.reddit.com | modern_web_app | Complex app, rendering decision |
| 3 | https://example.com | static_ssr | HTTP-only, no Playwright |
| 4 | https://httpbin.org/html | strong_html | HTTP-only, complete HTML |
| 5 | https://vuejs.org | javascript_heavy | May trigger browser fallback |
| 6 | https://nextjs.org | nextjs_react | Next.js/React, rendering decision |
| 7 | http://github.com | redirects | HTTP -> HTTPS redirect |
| 8 | https://httpbin.org/status/200 | weak_seo_metadata | Minimal response |
| 9 | https://httpbin.org/links/5/0 | links_test | Known internal/external links |
| 10 | https://example.com | images | Asset extraction |
| 11 | https://invalid.url.that.does.not.exist.example | invalid_url | Expected failure |
| 12 | https://httpbin.org/json | non_html | JSON, no Playwright |
| 13 | https://example.com/#section | fragment | Fragment identifier |
| 14 | https://example.com?utm_source=test&id=1 | query_params | Query parameters |
| 15 | https://httpbin.org/status/404 | http_error | 404 error |

## Output

Results are saved under `app/modules/crawler/tests/results/<normalized_domain>/`:

```
results/
├── cyfuture.com/
│   ├── summary.json
│   ├── result.json
│   ├── initial.html
│   ├── final.html
│   └── errors.log
├── www.reddit.com/
│   └── ...
└── ...
```

## Pipeline Stages Logged

For each URL, the test logs:

1. **INPUT** — Original URL
2. **URL NORMALIZATION** — Original vs normalized
3. **HTTP FETCHER** — Status, final URL, content-type, size, timing, redirects
4. **RENDER DETECTOR** — Decision (HTTP/BROWSER), reason, details
5. **SMART FETCHER** — Initial mode, browser fallback, final mode
6. **PLAYWRIGHT** — Executed, status, final URL, render time
7. **PARSER** — Title, H1/H2 count, word count, links, images
8. **SEO DATA** — Title, meta description, canonical, robots, H1, hreflang
9. **LINKS** — Total, internal, external, samples
10. **IMAGES** — Total, missing alt, lazy loaded
11. **FINAL RESULT** — Pass/fail with reason

## Notes

- **Do not modify production code.** This harness only adds test files.
- Network requests are made to real public URLs. Run responsibly.
- Results are saved as JSON/HTML for manual inspection.
- A test "passes" only when the expected crawler pipeline behavior is verified.
