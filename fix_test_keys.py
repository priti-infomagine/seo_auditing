fp = 'app/tests/test_lighthouse_check.py'
src = open(fp, encoding='utf-8').read()

# Fix JSON body keys: "devices" -> "device" (but only in the json= request bodies, not in assertions)
# The JSON request body key should be "device", not "devices"
# But we need to be careful not to change assertions that check data["devices"]

# Fix the test_request JSON keys (inside json={})
src = src.replace('"devices": ["mobile"]', '"device": ["mobile"]')
src = src.replace('"devices": ["desktop"]', '"device": ["desktop"]')
src = src.replace('"devices": ["mobile", "desktop"]', '"device": ["mobile", "desktop"]')

# Fix crawl_config keys (in test jobs, the crawl_config stores "devices" as the key)
# These should stay as "devices" in crawl_config since that's what services.py stores
# Actually, looking at the test code, the crawl_config in tests creates CrawlJob directly
# and the services.py prepare_check now stores "devices" in crawl_config
# So the test assertions should check crawl_config["devices"] not crawl_config["device"]
# The replace above already handled this for the JSON body, but we also need to make sure
# crawl_config assertions use "devices"

# The assertion `job.crawl_config["devices"] == ["mobile"]` was already updated by our earlier script

open(fp, 'w', encoding='utf-8').write(src)
print("Fixed JSON body keys in tests")
print("Checking remaining devices references...")

# Show any remaining "devices" in JSON request bodies
lines = src.split('\n')
for i, line in enumerate(lines, 1):
    if ('json=' in line or 'json={' in line) and '"devices"' in line:
        print(f"  Still has devices in json body at line {i}: {line.strip()}")
    if 'crawl_config' in line and '"device"' in line and '"devices"' not in line:
        print(f"  crawl_config with device (not devices) at line {i}: {line.strip()}")
