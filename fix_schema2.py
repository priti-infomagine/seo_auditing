fp = 'app/modules/seprate_checks/google_lighthouse_check/schema.py'
src = open(fp, encoding='utf-8').read()

# Update LighthouseCheckQueuedResponse device field
old_queued_device = '''    device: str = Field(
        ...,
        description="The device strategy for the check (mobile/desktop)",
    )
    categories: List[str] = Field(
        ...,
        description="The Lighthouse categories requested",
    )
    status_url: str = Field('''
new_queued_device = '''    devices: List[str] = Field(
        ...,
        description="The device strategies for the check (mobile/desktop)",
    )
    categories: List[str] = Field(
        ...,
        description="The Lighthouse categories requested",
    )
    version: Optional[List[str]] = Field(
        None,
        description="The Lighthouse versions requested",
    )
    status_url: str = Field('''

assert old_queued_device in src, "Could not find LighthouseCheckQueuedResponse device field"
src = src.replace(old_queued_device, new_queued_device)

# Update LighthouseCheckStatusResponse device field
old_status_device = '''    device: str = Field(
        ...,
        description="The device strategy for the check",
    )
    categories: List[str] = Field('''
new_status_device = '''    devices: List[str] = Field(
        ...,
        description="The device strategies for the check",
    )
    categories: List[str] = Field('''

assert old_status_device in src, "Could not find LighthouseCheckStatusResponse device field"
src = src.replace(old_status_device, new_status_device)

open(fp, 'w', encoding='utf-8').write(src)
print("schema.py response models updated successfully")
