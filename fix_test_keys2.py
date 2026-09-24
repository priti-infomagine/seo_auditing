fp = 'app/tests/test_lighthouse_check.py'
src = open(fp, encoding='utf-8').read()

# The problem: fix_crawl_config.py changed ALL "device": [...] to "devices": [...]
# But JSON request bodies should use "device" (the Pydantic field name)
# Only crawl_config dicts should use "devices"

# Strategy: 
# 1. First, change all "devices" back to "device" everywhere
src = src.replace('"devices":', '"device":')

# 2. Then specifically change crawl_config entries to use "devices"
# We need to identify crawl_config contexts. These are in patterns like:
# crawl_config={"phase": ..., "task_id": ..., "device": [...], ...}
# and crawl_config={\n  "phase": ...,\n  "device": [...]\n}

# For crawl_config dict entries, the key should be "devices" not "device"
# Let's find all crawl_config contexts and fix them

lines = src.split('\n')
new_lines = []
in_crawl_config = False
brace_depth = 0

for i, line in enumerate(lines):
    stripped = line.strip()
    
    # Detect entering crawl_config (single or multi-line)
    if 'crawl_config' in line and ('={' in line or '= {' in line):
        in_crawl_config = True
        brace_depth = stripped.count('{') - stripped.count('}')
        if brace_depth <= 0 and '}' in stripped:
            in_crawl_config = False
    
    # If we're inside a crawl_config, replace "device" with "devices"
    if in_crawl_config and '"device":' in stripped and '"devices":' not in stripped:
        line = line.replace('"device":', '"devices":')
    
    # Track brace depth for multi-line crawl_config
    if in_crawl_config:
        brace_depth += stripped.count('{') - stripped.count('}')
        if brace_depth <= 0:
            in_crawl_config = False
    
    new_lines.append(line)

src = '\n'.join(new_lines)

open(fp, 'w', encoding='utf-8').write(src)
print("Fixed test file - JSON bodies use 'device', crawl_config uses 'devices'")

# Verify
lines = src.split('\n')
issues = []
for i, line in enumerate(lines, 1):
    if '"devices":' in line:
        # Check if this is in a crawl_config context
        context_start = max(0, i-10)
        context_end = min(len(lines), i+10)
        context = lines[context_start:context_end]
        has_config = any('crawl_config' in l for l in context)
        has_json = any('json=' in l for l in context)
        if not has_config and has_json:
            issues.append(f"  WARNING line {i}: devices in JSON body: {line.strip()}")
        elif not has_config and not has_json and not any('crawl_config' in l for l in context):
            # Could be in response assertion (data["devices"] or d["devices"])
            if 'data["devices"]' not in line and 'd["devices"]' not in line:
                issues.append(f"  WARNING line {i}: unknown context: {line.strip()}")

if issues:
    for issue in issues:
        print(issue)
else:
    print("  All 'devices' references are in correct contexts (crawl_config or response assertions)")
