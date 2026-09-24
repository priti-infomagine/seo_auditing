from app.modules.seprate_checks.google_lighthouse_check.schema import (
    LighthouseCheckRequest,
    LighthouseCheckQueuedResponse,
    LighthouseCheckStatusResponse,
)

print("Testing LighthouseCheckRequest:")

# Test single device string
req = LighthouseCheckRequest(url="https://example.com/", device="mobile")
print(f"  device='mobile' -> device={req.device}, effective_devices={req.effective_devices}")
assert req.effective_devices == ["mobile"]

# Test list of devices
req = LighthouseCheckRequest(url="https://example.com/", device=["mobile", "desktop"])
print(f"  device=['mobile', 'desktop'] -> effective_devices={req.effective_devices}")
assert req.effective_devices == ["mobile", "desktop"]

# Test version
req = LighthouseCheckRequest(url="https://example.com/", device="mobile", version="7")
print(f"  version='7' -> version={req.version}")
assert req.version == ["7"]

# Test version list
req = LighthouseCheckRequest(url="https://example.com/", device="mobile", version=["6", "7"])
print(f"  version=['6', '7'] -> version={req.version}")
assert req.version == ["6", "7"]

# Test invalid device
try:
    req = LighthouseCheckRequest(url="https://example.com/", device="tablet")
    print("  ERROR: should have raised for tablet")
except Exception as e:
    print(f"  Correctly rejected device='tablet': {type(e).__name__}")

# Test invalid version
try:
    req = LighthouseCheckRequest(url="https://example.com/", device="mobile", version="99")
    print("  ERROR: should have raised for version 99")
except Exception as e:
    print(f"  Correctly rejected version='99': {type(e).__name__}")

print("\nTesting LighthouseCheckQueuedResponse:")
resp = LighthouseCheckQueuedResponse(
    success=True,
    status="queued",
    message="test",
    check_id="12345678-1234-1234-1234-123456789012",
    task_id="task-123",
    url="https://example.com/",
    domain="example.com",
    devices=["mobile"],
    categories=["performance"],
    version=["7"],
    status_url="/api/v1/lighthouse/status/123",
    result_url="/api/v1/lighthouse/results/123",
)
print(f"  devices={resp.devices}, version={resp.version}")
assert resp.devices == ["mobile"]
assert resp.version == ["7"]

print("\nAll schema tests passed!")
