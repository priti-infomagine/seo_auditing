fp = 'app/tests/test_lighthouse_check.py'
src = open(fp, encoding='utf-8').read()

# Show all lines with device references
lines = src.split('\n')
for i, line in enumerate(lines, 1):
    if 'device' in line.lower() and ("\"mobile\"" in line or "\"desktop\"" in line or 'device=') :
        if 'devices' not in line.lower() and 'normalize_device' not in line and 'effected_device' not in line:
            print(f"Line {i}: {line.rstrip()}")
