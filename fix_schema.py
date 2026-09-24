import re as _re

fp = 'app/modules/seprate_checks/google_lighthouse_check/schema.py'
src = open(fp, encoding='utf-8').read()

# 1. Update imports - add Union
old_typing = 'from typing import Optional, List'
new_typing = 'from typing import Optional, List, Union'

assert old_typing in src, "Could not find old typing import"
src = src.replace(old_typing, new_typing)

# 2. Update imports from validation
old_imports = '''from app.modules.seprate_checks.google_lighthouse_check.validation import (
    DEFAULT_CATEGORIES,
    normalize_categories,
    normalize_device,
    validate_max_pages,
    validate_url,
)'''
new_imports = '''from app.modules.seprate_checks.google_lighthouse_check.validation import (
    DEFAULT_CATEGORIES,
    DEFAULT_DEVICES,
    normalize_categories,
    normalize_devices,
    normalize_device,
    validate_max_pages,
    validate_url,
    validate_versions,
)'''

assert old_imports in src, "Could not find old validation imports"
src = src.replace(old_imports, new_imports)

# 3. Update device field to accept Union[str, List[str]]
old_device_field = '''    device: str = Field(
        ...,
        description="The device type for the check ('mobile' or 'desktop')",
    )'''
new_device_field = '''    device: Union[str, List[str]] = Field(
        ...,
        description=(
            "Device strategy for the check. Accepts a single string "
            "('mobile' or 'desktop') or a list of them (e.g. "
            "['mobile', 'desktop']). Defaults to both when None/empty."
        ),
    )'''

assert old_device_field in src, "Could not find old device field"
src = src.replace(old_device_field, new_device_field)

# 4. Update version field
old_version_field = '''    version: Optional[str] = Field(
        None,
        description="Lighthouse version hint (currently unused)",
    )'''
new_version_field = '''    version: Optional[Union[str, List[str]]] = Field(
        None,
        description=(
            "Lighthouse version(s). Accepts a single version string "
            "(e.g. '7') or a list (e.g. ['6', '7']). Defaults to all "
            "when None/empty."
        ),
    )'''

assert old_version_field in src, "Could not find old version field"
src = src.replace(old_version_field, new_version_field)

# 5. Update device validator to use normalize_devices
old_device_validator = '''    @field_validator("device")
    @classmethod
    def _validate_device(cls, v: str) -> str:
        return normalize_device(v)'''
new_device_validator = '''    @field_validator("device")
    @classmethod
    def _validate_device(cls, v: Union[str, List[str]]) -> List[str]:
        return normalize_devices(v)'''

assert old_device_validator in src, "Could not find old device validator"
src = src.replace(old_device_validator, new_device_validator)

# 6. Add effective_devices property after effective_category
old_effective = '''    @property
    def effective_category(self) -> List[str]:
        return self.category or list(DEFAULT_CATEGORIES)'''
new_effective = '''    @property
    def effective_category(self) -> List[str]:
        return self.category or list(DEFAULT_CATEGORIES)

    @property
    def effective_devices(self) -> List[str]:
        """Return the normalized list of device strategies."""
        return normalize_devices(self.device)'''

assert old_effective in src, "Could not find old effective_category"
src = src.replace(old_effective, new_effective)

open(fp, 'w', encoding='utf-8').write(src)
print("schema.py updated successfully")
