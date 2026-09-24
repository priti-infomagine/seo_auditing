fp = 'app/modules/seprate_checks/google_lighthouse_check/router.py'
src = open(fp, encoding='utf-8').read()

# 1. Update prepare_check call to pass version
old_prepare_call = '''        setup = await service.prepare_check(
            db=db,
            url=body.url,
            device=body.device,
            max_pages=body.max_pages,
            category=body.effective_category,
            pagespeed_concurrency=service.PAGESPEED_CONCURRENCY,
        )'''
new_prepare_call = '''        setup = await service.prepare_check(
            db=db,
            url=body.url,
            device=body.device,
            max_pages=body.max_pages,
            category=body.effective_category,
            version=body.version,
            pagespeed_concurrency=service.PAGESPEED_CONCURRENCY,
        )'''

assert old_prepare_call in src, "Could not find old prepare_check call"
src = src.replace(old_prepare_call, new_prepare_call)

# 2. Update Celery task kwargs to pass version
old_task_kwargs = '''            kwargs={
                "category": setup["categories"],
                "pagespeed_concurrency": setup["pagespeed_concurrency"],
            },'''
new_task_kwargs = '''            kwargs={
                "category": setup["categories"],
                "version": setup["version"],
                "pagespeed_concurrency": setup["pagespeed_concurrency"],
            },'''

assert old_task_kwargs in src, "Could not find old task kwargs"
src = src.replace(old_task_kwargs, new_task_kwargs)

# 3. Update logger.info to include version
old_logger = '''    logger.info(
        f"POST /lighthouse/check — url={body.url}, device={body.device}, "
        f"max_pages={body.max_pages}, category={body.effective_category}"
    )'''
new_logger = '''    logger.info(
        f"POST /lighthouse/check — url={body.url}, devices={body.effective_devices}, "
        f"max_pages={body.max_pages}, category={body.effective_category}, version={body.version}"
    )'''

assert old_logger in src, "Could not find old logger"
src = src.replace(old_logger, new_logger)

# 4. Update LighthouseCheckQueuedResponse construction
old_response = '''    return LighthouseCheckQueuedResponse(
        success=True,
        status="queued",
        message="Lighthouse check queued successfully — poll the status URL for progress",
        check_id=UUID(check_id),
        task_id=async_result.id,
        url=setup["url"],
        domain=setup["domain"],
        device=setup["device"],
        categories=setup["categories"],
        status_url=f"/api/v1/lighthouse/status/{check_id}",
        result_url=f"/api/v1/lighthouse/results/{check_id}",
    )'''
new_response = '''    return LighthouseCheckQueuedResponse(
        success=True,
        status="queued",
        message="Lighthouse check queued successfully — poll the status URL for progress",
        check_id=UUID(check_id),
        task_id=async_result.id,
        url=setup["url"],
        domain=setup["domain"],
        devices=setup["devices"],
        categories=setup["categories"],
        version=setup["version"],
        status_url=f"/api/v1/lighthouse/status/{check_id}",
        result_url=f"/api/v1/lighthouse/results/{check_id}",
    )'''

assert old_response in src, "Could not find old response construction"
src = src.replace(old_response, new_response)

# 5. Update status endpoint to use devices from crawl_config
old_status_device = '            device=(job.crawl_config or {}).get("device", "mobile"),'
new_status_device = '            devices=(job.crawl_config or {}).get("devices", ["mobile", "desktop"]),'

assert old_status_device in src, "Could not find old status device"
src = src.replace(old_status_device, new_status_device)

open(fp, 'w', encoding='utf-8').write(src)
print("router.py updated successfully")
