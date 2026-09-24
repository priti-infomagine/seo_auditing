fp = 'app/tests/test_lighthouse_check.py'
src = open(fp, encoding='utf-8').read()

# Strategy: Do global string replacements for all device-related patterns
# 1. JSON body device -> devices list
# Replace: "device": "mobile" -> "devices": ["mobile"]
src = src.replace('"device": "mobile"', '"devices": ["mobile"]')

# Replace: "device": "desktop" -> "devices": ["desktop"]
src = src.replace('"device": "desktop"', '"devices": ["desktop"]')

# 2. Response assertions: data["device"] -> data["devices"]
# These are already partially replaced but let's catch any remaining
src = src.replace('data["device"] == "mobile"', 'data["devices"] == ["mobile"]')
src = src.replace('data["device"] == "desktop"', 'data["devices"] == ["desktop"]')

# 3. crawl_config assertions
src = src.replace('job.crawl_config["device"] == "mobile"', 'job.crawl_config["devices"] == ["mobile"]')

# 4. run_check_async calls - device="mobile" -> device=["mobile"]
src = src.replace('device="mobile"', 'device=["mobile"]')
src = src.replace('device="desktop"', 'device=["desktop"]')

# 5. Status assertions in test_status_lifecycle_phases - already partially done
# Let's check what's there now: assert d["device"] == ...
# The status endpoint now returns devices, not device
# But d["device"] assertions need to be changed to d["devices"]
src = src.replace('d["device"] == "mobile"', 'd["devices"] == ["mobile"]')
src = src.replace('d["device"] == "desktop"', 'd["devices"] == ["desktop"]')

# 6. Status assertions for d["devices"] in lifecycle test (already added)
# Need to check if d["devices"] assertions exist for crawl phase tests

# 7. Update status response assertions
# In test_status_queued, we already added devices assertion

# 8. For the test_run_check_async_end_to_end result assertion
# result["device"] should be result["device"] == ["mobile"]
src = src.replace(
    'assert result["status"] == "completed"\n    assert result["pagespeed_total"] == 3',
    'assert result["status"] == "completed"\n    assert result["device"] == ["mobile"]\n    assert result["pagespeed_total"] == 3'
)

# 9. Add version test cases at the end
version_tests = '''

# -- Version parameter tests --


@pytest.mark.asyncio
async def test_check_with_single_version(mock_celery):
    """A single version string is normalized into a list and passed through."""
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={
                "url": "https://example.com/",
                "device": ["mobile"],
                "version": "7",
            },
        )

    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["version"] == ["7"]

    sent = captured[0]
    assert sent["kwargs"]["version"] == ["7"]


@pytest.mark.asyncio
async def test_check_with_version_list(mock_celery):
    """A list of version strings is passed through as-is."""
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={
                "url": "https://example.com/",
                "device": ["mobile", "desktop"],
                "version": ["6", "7"],
            },
        )

    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["version"] == ["6", "7"]

    sent = captured[0]
    assert sent["kwargs"]["version"] == ["6", "7"]


@pytest.mark.asyncio
async def test_check_with_invalid_version_returns_422(mock_celery):
    """An invalid version string triggers a 422 response."""
    async with await _client() as client:
        resp = await client.post(
            "/api/v1/lighthouse/check",
            json={
                "url": "https://example.com/",
                "device": ["mobile"],
                "version": "99",
            },
        )

    assert resp.status_code == 422
'''

src = src.rstrip() + version_tests

open(fp, 'w', encoding='utf-8').write(src)
print("test_lighthouse_check.py updated successfully")
print(f"File length: {len(src)} chars, {len(src.split(chr(10)))} lines")
