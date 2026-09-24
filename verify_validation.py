from app.modules.seprate_checks.google_lighthouse_check.validation import (
    normalize_devices,
    validate_versions,
    LighthouseValidationError,
    DEFAULT_DEVICES,
    ALLOWED_VERSIONS,
)

# Test normalize_devices
print("Testing normalize_devices:")

# Test single valid string
result = normalize_devices("mobile")
print(f"  normalize_devices('mobile') = {result}")
assert result == ["mobile"]

# Test list of valid strings
result = normalize_devices(["mobile", "desktop"])
print(f"  normalize_devices(['mobile', 'desktop']) = {result}")
assert result == ["mobile", "desktop"]

# Test empty list -> defaults
result = normalize_devices([])
print(f"  normalize_devices([]) = {result}")
assert result == DEFAULT_DEVICES

# Test None -> defaults
result = normalize_devices(None)
print(f"  normalize_devices(None) = {result}")
assert result == DEFAULT_DEVICES

# Test invalid device
try:
    normalize_devices("tablet")
    print("  ERROR: should have raised")
except LighthouseValidationError as e:
    print(f"  Correctly rejected 'tablet': {e}")

# Test invalid device in list
try:
    normalize_devices(["mobile", "tablet"])
    print("  ERROR: should have raised")
except LighthouseValidationError as e:
    print(f"  Correctly rejected ['mobile', 'tablet']: {e}")

# Test deduplication
result = normalize_devices(["mobile", "mobile", "desktop"])
print(f"  normalize_devices(['mobile', 'mobile', 'desktop']) = {result}")
assert result == ["mobile", "desktop"]

print()
print("Testing validate_versions:")

# Test single version
result = validate_versions("7")
print(f"  validate_versions('7') = {result}")
assert result == ["7"]

# Test list of versions
result = validate_versions(["6", "7"])
print(f"  validate_versions(['6', '7']) = {result}")
assert result == ["6", "7"]

# Test None
result = validate_versions(None)
print(f"  validate_versions(None) = {result}")
assert result is None

# Test empty list
result = validate_versions([])
print(f"  validate_versions([]) = {result}")
assert result is None

# Test invalid version
try:
    validate_versions("99")
    print("  ERROR: should have raised")
except LighthouseValidationError as e:
    print(f"  Correctly rejected '99': {e}")

# Test invalid version (non-numeric)
try:
    validate_versions("abc")
    print("  ERROR: should have raised")
except LighthouseValidationError as e:
    print(f"  Correctly rejected 'abc': {e}")

print()
print("All validation tests passed!")
