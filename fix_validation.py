import re as _re

fp = 'app/modules/seprate_checks/google_lighthouse_check/validation.py'
src = open(fp, encoding='utf-8').read()

# 1. Add Union import and DEFAULT_DEVICES, ALLOWED_VERSIONS, DEFAULT_VERSIONS, _VERSION_PATTERN
old_imports = 'from typing import List, Optional\nimport re\n\nfrom app.shared.utils.url_utils import normalize_url\n\n# \u2500\u2500 Allowed device strategies (PageSpeed Insights `strategy` param) \u2500\u2500\u2500\u2500\u2500\nALLOWED_DEVICES: tuple[str, ...] = ("mobile", "desktop")'
new_imports = 'from typing import List, Optional\nfrom typing import Union\nimport re\n\nfrom app.shared.utils.url_utils import normalize_url\n\n# \u2500\u2500 Allowed device strategies (PageSpeed Insights `strategy` param) \u2500\u2500\u2500\u2500\u2500\nALLOWED_DEVICES: tuple[str, ...] = ("mobile", "desktop")\nDEFAULT_DEVICES: List[str] = list(ALLOWED_DEVICES)\n\n# \u2500\u2500 Allowed Lighthouse versions \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nALLOWED_VERSIONS: tuple[str, ...] = ("1", "2", "3", "4", "5", "6", "7")\nDEFAULT_VERSIONS: List[str] = list(ALLOWED_VERSIONS)\n_VERSION_PATTERN = re.compile(r"^[1-9][0-9]*$")'

assert old_imports in src, "Could not find old imports block"
src = src.replace(old_imports, new_imports)

# 2. Add normalize_devices after normalize_device
old_normalize_device_end = '''    return lower


def validate_url(url: str) -> str:'''
new_normalize_device_end = '''    return lower


def normalize_devices(
    device: Union[str, List[str]]
) -> List[str]:
    """
    Normalize + validate the ``device`` request field.

    Accepts either a single string ("mobile") or a list of strings
    (["mobile", "desktop"]).  Returns a deduplicated, validated list of
    device strategies.  When ``device`` is None / empty, returns the full
    default set so behavior matches the original single-string default.
    """
    if device is None:
        return list(DEFAULT_DEVICES)

    # Single string -> wrap in a list
    if isinstance(device, str):
        devices = [device]
    elif isinstance(device, (list, tuple)):
        devices = list(device)
    else:
        raise LighthouseValidationError(
            f"device must be a string or list of strings, got {type(device).__name__}"
        )

    if len(devices) == 0:
        return list(DEFAULT_DEVICES)

    normalized: List[str] = []
    for dev in devices:
        if not isinstance(dev, str):
            raise LighthouseValidationError(
                f"device entry must be a string, got {type(dev).__name__}"
            )
        lower = dev.strip().lower()
        if lower not in ALLOWED_DEVICES:
            raise LighthouseValidationError(
                f"Invalid device '{dev}'. Allowed: {', '.join(ALLOWED_DEVICES)}"
            )
        if lower not in normalized:
            normalized.append(lower)

    return normalized


def validate_versions(version: Optional[Union[str, List[str]]]) -> Optional[List[str]]:
    """
    Validate + normalize the ``version`` field.

    Accepts a single version string (e.g. "1") or a list of version strings
    (e.g. ["1", "2", "6"]).  Each version must match the numeric pattern
    and be in ``ALLOWED_VERSIONS``.  Returns a deduplicated list, or None
    when no version is specified (meaning "use the default / all versions").
    """
    if version is None:
        return None

    # Single string -> wrap in a list
    if isinstance(version, str):
        versions = [version]
    elif isinstance(version, (list, tuple)):
        versions = list(version)
    else:
        raise LighthouseValidationError(
            f"version must be a string or list of strings, got {type(version).__name__}"
        )

    if len(versions) == 0:
        return None

    normalized: List[str] = []
    for ver in versions:
        if not isinstance(ver, str):
            raise LighthouseValidationError(
                f"version entry must be a string, got {type(ver).__name__}"
            )
        stripped = ver.strip()
        if not _VERSION_PATTERN.fullmatch(stripped):
            raise LighthouseValidationError(
                f"Invalid version '{ver}'. Must be a positive integer as a string."
            )
        if stripped not in ALLOWED_VERSIONS:
            raise LighthouseValidationError(
                f"Invalid version '{ver}'. Allowed: {', '.join(ALLOWED_VERSIONS)}"
            )
        if stripped not in normalized:
            normalized.append(stripped)

    return normalized


def validate_url(url: str) -> str:'''

assert old_normalize_device_end in src, "Could not find normalize_device end block"
src = src.replace(old_normalize_device_end, new_normalize_device_end)

# 3. Update validate_lighthouse_request signature and body
old_validate = '''def validate_lighthouse_request(
    url: str,
    device: str,
    category: Optional[List[str]],
    max_pages: Optional[int],
) -> dict:
    """
    Validate a full lighthouse check request.

    Returns a normalized dict:
        {url, device, category (list[str]), max_pages (int)}
    """
    return {
        "url": validate_url(url),
        "device": normalize_device(device),
        "category": normalize_categories(category),
        "max_pages": validate_max_pages(max_pages),
    }'''

new_validate = '''def validate_lighthouse_request(
    url: str,
    device: Union[str, List[str]],
    category: Optional[List[str]],
    max_pages: Optional[int],
    version: Optional[Union[str, List[str]]] = None,
) -> dict:
    """
    Validate a full lighthouse check request.

    Returns a normalized dict:
        {url, device (list[str]), category (list[str]), max_pages (int), version (list[str] or None)}
    """
    return {
        "url": validate_url(url),
        "device": normalize_devices(device),
        "category": normalize_categories(category),
        "max_pages": validate_max_pages(max_pages),
        "version": validate_versions(version),
    }'''

assert old_validate in src, "Could not find validate_lighthouse_request block"
src = src.replace(old_validate, new_validate)

open(fp, 'w', encoding='utf-8').write(src)
print("validation.py updated successfully")
print(f"File size: {len(src)} chars")
