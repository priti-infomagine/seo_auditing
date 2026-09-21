import os, sys

base = r"i:\PROJECTS\Automated SEO & Website Audit Tool\backend"
os.chdir(base)

checks = [
    "app/models/crawler_models/crawl_errors.py",
    "app/models/crawler_models/__init__.py",
    "app/services/crawler",
    "app/services/crawler/__init__.py",
    "app/services/crawler/crawl_service.py",
    "app/services/crawler/crawler.py",
    "app/storage/crawler",
    "app/services/parser",
    "app/services/scorer",
    "app/models/crawler_models/page_snapshots.py",
    "app/apis/endpoints/v1/crawler/__init__.py",
    "app/tests/test_server.py",
]

for c in checks:
    full = os.path.join(base, c)
    exists = os.path.exists(full)
    size = os.path.getsize(full) if (exists and os.path.isfile(full)) else "N/A"
    isfile = os.path.isfile(full) if exists else False
    print(f"{c}: exists={exists}, isfile={isfile}, size={size}")

# Check if there's a venv active
print(f"\nPython: {sys.executable}")
print(f"CWD: {os.getcwd()}")
