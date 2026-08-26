# # 1. Remove MOCK endpoint
# Remove-Item -Path "app/api/endpoints/v1/audit/audit.py" -Force

# # 2. Remove file-based parser endpoint  
# Remove-Item -Path "app/api/endpoints/v1/parser/parse.py" -Force

# # 3. Remove file-based scorer endpoint
# Remove-Item -Path "app/api/endpoints/v1/scorer/score.py" -Force

# # 4. Remove test endpoints
# Remove-Item -Path "app/api/endpoints/v1/celery_test.py" -Force
# Remove-Item -Path "app/api/endpoints/v1/crawler/test_crawl.py" -Force

# # 5. Remove redundant services
# Remove-Item -Path "app/modules/parser/services/batch_parser_service.py" -Force
# Remove-Item -Path "app/modules/parser/services/parser_service.py" -Force
# Remove-Item -Path "app/modules/parser/services/parse_storage.py" -Force
# Remove-Item -Path "app/modules/parser/services/pseud_parse_service.py" -Force
# Remove-Item -Path "app/modules/crawler/crawl_service.py" -Force