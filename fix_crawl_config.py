fp = 'app/tests/test_lighthouse_check.py'
src = open(fp, encoding='utf-8').read()

# Fix crawl_config entries - they should use "devices" not "device"
src = src.replace('"device": ["mobile"]', '"devices": ["mobile"]')
src = src.replace('"device": ["desktop"]', '"devices": ["desktop"]')

open(fp, 'w', encoding='utf-8').write(src)
print("Fixed crawl_config keys in tests")

# Verify
lines = src.split('\n')
remaining = 0
for i, line in enumerate(lines, 1):
    if 'crawl_config' in line and '"device"' in line:
        if '"devices"' not in line and '"device":' in line:
            print(f"  Still has device in crawl_config at line {i}: {line.strip()}")
            remaining += 1
print(f"Remaining crawl_config device (not devices) entries: {remaining}")
