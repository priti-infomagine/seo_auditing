fp = 'app/modules/seprate_checks/google_lighthouse_check/services.py'
src = open(fp, encoding='utf-8').read()

# Helper: apply replacements in order
replacements = []

# 1. Update typing import
replacements.append((
    'from typing import Callable, Optional',
    'from typing import Callable, Optional, Union'
))

# 2. Update validation imports
replacements.append((
    '''from app.modules.seprate_checks.google_lighthouse_check.validation import (
    DEFAULT_CATEGORIES,
    normalize_categories,
    normalize_device,
    validate_max_pages,
    validate_url,
)''',
    '''from app.modules.seprate_checks.google_lighthouse_check.validation import (
    DEFAULT_CATEGORIES,
    DEFAULT_DEVICES,
    normalize_categories,
    normalize_devices,
    normalize_device,
    validate_max_pages,
    validate_url,
    validate_versions,
)'''
))

# 3. Update prepare_check signature
replacements.append((
    '''    async def prepare_check(
        self,
        db: AsyncSession,
        url: str,
        device: str,
        max_pages: int,
        category: Optional[list[str]],
        pagespeed_concurrency: int = PAGESPEED_CONCURRENCY,
    ) -> dict:''',
    '''    async def prepare_check(
        self,
        db: AsyncSession,
        url: str,
        device: Union[str, List[str]],
        max_pages: Optional[int],
        category: Optional[list[str]],
        version: Optional[Union[str, List[str]]] = None,
        pagespeed_concurrency: int = PAGESPEED_CONCURRENCY,
    ) -> dict:'''
))

# 4. Update prepare_check body - normalize device and add version
replacements.append((
    '''        normalized_url = validate_url(url)
        device_norm = normalize_device(device)
        categories = normalize_categories(category) or list(DEFAULT_CATEGORIES)
        effective_max_pages = validate_max_pages(max_pages)

        check_id = uuid4()
        domain = get_domain(normalized_url) or "unknown"
        device_enum = Device(device_norm)''',
    '''        normalized_url = validate_url(url)
        devices = normalize_devices(device)
        categories = normalize_categories(category) or list(DEFAULT_CATEGORIES)
        version_norm = validate_versions(version)
        effective_max_pages = validate_max_pages(max_pages)

        check_id = uuid4()
        domain = get_domain(normalized_url) or "unknown"
        device_enums = [Device(d) for d in devices]'''
))

# 5. Update crawl_config device field
replacements.append((
    '            "device": device_enum.value,',
    '            "devices": [d.value for d in device_enums],'
))

# 6. Update logger in prepare_check
replacements.append((
    '''        logger.info(
            f"LighthouseCheckService: prepared check_id={check_id}, domain={domain}, "
            f"device={device_enum.value}, max_pages={effective_max_pages}"
        )''',
    '''        logger.info(
            f"LighthouseCheckService: prepared check_id={check_id}, domain={domain}, "
            f"devices={[d.value for d in device_enums]}, max_pages={effective_max_pages}, "
            f"version={version_norm}"
        )'''
))

# 7. Update prepare_check return
replacements.append((
    '''        return {
            "check_id": str(check_id),
            "domain": domain,
            "url": normalized_url,
            "device": device_enum.value,
            "categories": categories,
            "max_pages": effective_max_pages,
            "pagespeed_concurrency": pagespeed_concurrency,
        }''',
    '''        return {
            "check_id": str(check_id),
            "domain": domain,
            "url": normalized_url,
            "device": [d.value for d in device_enums],
            "categories": categories,
            "max_pages": effective_max_pages,
            "version": version_norm,
            "pagespeed_concurrency": pagespeed_concurrency,
        }'''
))

# 8. Update run_check_async signature
replacements.append((
    '''    async def run_check_async(
        self,
        check_id: UUID,
        url: str,
        device: str,
        max_pages: int,
        category: Optional[list[str]] = None,
        pagespeed_concurrency: int = PAGESPEED_CONCURRENCY,
        update_state: Optional[Callable[[str, dict], None]] = None,
    ) -> dict:''',
    '''    async def run_check_async(
        self,
        check_id: UUID,
        url: str,
        device: Union[str, List[str]],
        max_pages: int,
        category: Optional[list[str]] = None,
        version: Optional[Union[str, List[str]]] = None,
        pagespeed_concurrency: int = PAGESPEED_CONCURRENCY,
        update_state: Optional[Callable[[str, dict], None]] = None,
    ) -> dict:'''
))

# 9. Update run_check_async body
replacements.append((
    '''        start = time.time()
        device_enum = Device(device.lower())
        categories = category or [
            "performance", "seo", "best-practices", "accessibility",
        ]
        domain = get_domain(url) or "unknown"''',
    '''        start = time.time()
        devices = normalize_devices(device)
        device_enums = [Device(d) for d in devices]
        categories = normalize_categories(category) or [
            "performance", "seo", "best-practices", "accessibility",
        ]
        version_norm = validate_versions(version)
        domain = get_domain(url) or "unknown"'''
))

# 10. Update total calculation
replacements.append((
    '''        total = len(crawled_urls)
        logger.info(
            f"LighthouseCheckService: crawl done for check_id={check_id}, "
            f"discovered {total} URLs — starting pagespeed phase"
        )''',
    '''        total = len(crawled_urls) * len(device_enums)
        logger.info(
            f"LighthouseCheckService: crawl done for check_id={check_id}, "
            f"discovered {len(crawled_urls)} URLs across {len(device_enums)} devices "
            f"— starting pagespeed phase ({total} checks)"
        )'''
))

# 11. Update strategy variable
replacements.append((
    '''                semaphore = asyncio.Semaphore(pagespeed_concurrency)
                strategy = device_enum.value''',
    '''                semaphore = asyncio.Semaphore(pagespeed_concurrency)'''
))

# 12. Update _check_one signature and body
replacements.append((
    '''                async def _check_one(target_url: str) -> tuple[str, Optional[dict], Optional[str]]:
                    async with semaphore:
                        try:
                            raw = await self.pagespeed_client.fetch(
                                url=target_url,
                                strategy=strategy,
                                category=categories,
                            )
                            parsed = PagespeedClient.parse_result(raw, target_url, strategy)''',
    '''                async def _check_one(target_url: str, strategy_device: Device) -> tuple[str, Optional[dict], Optional[str]]:
                    async with semaphore:
                        try:
                            raw = await self.pagespeed_client.fetch(
                                url=target_url,
                                strategy=strategy_device.value,
                                category=categories,
                            )
                            parsed = PagespeedClient.parse_result(raw, target_url, strategy_device.value)'''
))

# 13. Update upsert success
replacements.append((
    '''                            await results_repo.upsert(
                                check_id=check_id,
                                domain=domain,
                                url=parsed["url"],
                                device=device_enum,
                                status=PageStatus.SUCCESS,''',
    '''                            await results_repo.upsert(
                                check_id=check_id,
                                domain=domain,
                                url=parsed["url"],
                                device=strategy_device,
                                status=PageStatus.SUCCESS,'''
))

# 14. Update upsert failed
replacements.append((
    '''                            await results_repo.upsert(
                                check_id=check_id,
                                domain=domain,
                                url=done_url,
                                device=device_enum,
                                status=PageStatus.FAILED,
                                reason=err,
                            )''',
    '''                            await results_repo.upsert(
                                check_id=check_id,
                                domain=domain,
                                url=done_url,
                                device=strategy_device,
                                status=PageStatus.FAILED,
                                reason=err,
                            )'''
))

# 15. Update task creation - iterate over devices
replacements.append((
    '                tasks = [asyncio.ensure_future(_check_one(u)) for u in crawled_urls]',
    '''                tasks = [
                    asyncio.ensure_future(_check_one(u, dev))
                    for dev in device_enums
                    for u in crawled_urls
                ]'''
))

# 16. Update run_check_async return
replacements.append((
    '''                return {
                    "check_id": str(check_id),
                    "domain": domain,
                    "device": device,
                    "pagespeed_total": total,
                    "pagespeed_succeeded": succeeded,
                    "pagespeed_failed": failed,
                    "status": "completed",
                }''',
    '''                return {
                    "check_id": str(check_id),
                    "domain": domain,
                    "device": [d.value for d in device_enums],
                    "version": version_norm,
                    "pagespeed_total": total,
                    "pagespeed_succeeded": succeeded,
                    "pagespeed_failed": failed,
                    "status": "completed",
                }'''
))

# Apply all replacements
for i, (old, new) in enumerate(replacements):
    if old not in src:
        print(f"WARNING: replacement {i+1} not found in file")
        print(f"  Looking for: {old[:80]}...")
    else:
        src = src.replace(old, new)
        print(f"OK: replacement {i+1} applied")

open(fp, 'w', encoding='utf-8').write(src)
print("services.py updated successfully")
