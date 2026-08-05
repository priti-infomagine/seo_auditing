crawler/
│
├── crawler.py          # Fetches pages
├── parser.py           # Extracts raw HTML data
├── analyzer.py         # Runs SEO checks
├── scorer.py           # Computes SEO score
├── reporter.py         # Generates HTML/CSV/JSON reports
├── robots.py           # Parses robots.txt
├── sitemap.py          # Reads XML sitemaps
├── link_checker.py     # Validates internal/external links
└── site_audit.py       # Aggregates results across all pages

Crawler
      │
      ▼
Extract HTML
      │
      ▼
DataParser
      │
      ▼
Raw Data
      │
      ▼
SEO Analyzer
      │
      ▼
SEO Report
Step 1: Create an SEOAnalyzer

Don't put SEO logic inside DataParser.

For example, DataParser returns:

{
    "title": "Best SEO Guide",
    "meta_description": "...",
    "headings": {...},
    ...
}

Then SEOAnalyzer determines whether these are good or need improvement.

Example output:

{
    "title": {
        "status": "warning",
        "message": "Title too long (74 characters)"
    },
    "meta_description": {
        "status": "good"
    },
    "h1": {
        "status": "error",
        "message": "Missing H1"
    }
}
Step 2: Analyze Every Field

For example:

Title

Check

Missing
Too short (<30 chars)
Too long (>60 chars)

Output

{
    "score": 8,
    "issues": [
        "Title too short"
    ]
}
Meta Description

Check

Missing
Under 120 chars
Over 160 chars
H1

Check

Missing
More than one H1
Images

Check

without_alt > 0

If yes

Warning:
12 images are missing alt text.
Canonical

Check

Missing
Empty
Invalid
Robots

Check

noindex
nofollow

If present

Warning:
This page is not indexable.
Open Graph

Missing

og:title
og:image
og:description
Twitter Cards

Missing

twitter:card
twitter:title
Word Count

Example

<300 words

↓

Thin content

Reading Time

Example

1 minute

↓

Very little content

Heading Structure

Bad

H3
↑
No H2

Good

H1
 ├──H2
 │     ├──H3
Step 3: Give Every Check a Severity

For example

GOOD
WARNING
ERROR
INFO

Example

[
    {
        "type":"Title",
        "status":"good"
    },
    {
        "type":"Meta Description",
        "status":"warning"
    },
    {
        "type":"Canonical",
        "status":"error"
    }
]
Step 4: Calculate an SEO Score

Example

100 points total

Title              10
Description        10
H1                 10
Images             10
Canonical          10
Robots             10
Schema             10
Links              10
Social             10
Performance        20

Example

Final Score

87 / 100
Step 5: Give Suggestions

Instead of

Missing H1

Return

Missing H1.

Recommendation:
Add one descriptive H1 that summarizes the page.
Step 6: Categorize Results

Like Screaming Frog

Technical SEO

✓ HTTPS
✓ Canonical

⚠ Missing viewport

✗ No robots tag
Content

✓ Word count

⚠ Short title

✗ Duplicate H1
Media

⚠ 14 images without alt
Step 7: Crawl the Entire Site

After one page works

Homepage
     │
     ├── Blog
     ├── Docs
     ├── Contact
     └── About

Collect

every page
every title
every description
every H1
every canonical

Now you can detect

Duplicate titles
Duplicate descriptions
Duplicate H1s
Orphan pages
Broken internal links
Redirect chains
Deep pages (crawl depth)
Pages with no incoming links

These are site-level SEO issues that can't be found from a single page.

Step 8: Generate Reports

Produce outputs such as:

JSON (for APIs)
CSV (like Screaming Frog exports)
HTML report
PDF report
Dashboard
Step 9: Add Performance Metrics

Using Playwright, you can collect:

Response time
DOM load time
Number of requests
HTML size
JavaScript size
CSS size

Later, integrate Lighthouse for:

Largest Contentful Paint (LCP)
Cumulative Layout Shift (CLS)
Interaction to Next Paint (INP)
Step 10: Overall Architecture

A scalable project structure could look like this:

crawler/
│
├── crawler.py          # Fetches pages
├── parser.py           # Extracts raw HTML data
├── analyzer.py         # Runs SEO checks
├── scorer.py           # Computes SEO score
├── reporter.py         # Generates HTML/CSV/JSON reports
├── robots.py           # Parses robots.txt
├── sitemap.py          # Reads XML sitemaps
├── link_checker.py     # Validates internal/external links
└── site_audit.py       # Aggregates results across all pages


crawler/
│
├── crawler/
│   ├── fetcher.py
│   ├── queue.py
│   └── downloader.py
│
├── parser/
│   ├── html_parser.py
│   ├── content_parser.py
│   ├── image_parser.py
│   ├── link_parser.py
│   └── schema_parser.py
│
├── analyzer/
│   ├── title_checks.py
│   ├── meta_checks.py
│   ├── heading_checks.py
│   ├── content_checks.py
│   ├── image_checks.py
│   ├── technical_checks.py
│   ├── scoring.py
│   └── recommendations.py
│
├── storage/
│   ├── models.py
│   ├── repository.py
│   └── serializers.py
│
├── reports/
│   ├── json_report.py
│   ├── pdf_report.py
│   └── excel_report.py
│
└── api/