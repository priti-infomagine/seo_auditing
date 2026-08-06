"""
Asset service - validates and persists assets.
Business logic + validation + persistence coordination.
"""
from typing import List
from uuid import UUID

from app.services.crawler_service.extractors.asset_extractor import ExtractedAsset
from app.services.crawler_service.repositories.page_asset_repository import PageAssetRepository
from app.utils.crawler_utils.mime_detector import detect_mime_type
from app.models.crawler_models.page_assets import PageAsset


class AssetService:
    """Service for asset operations."""

    def __init__(self, db, page_id: UUID):
        self.repository = PageAssetRepository(db)
        self.page_id = page_id

    async def process_and_save_assets(
        self,
        extracted_assets: List[ExtractedAsset],
    ) -> List[PageAsset]:
        """
        Process extracted assets and save to database.

        Args:
            extracted_assets: List of ExtractedAsset objects

        Returns:
            List of saved PageAsset instances
        """
        saved_assets = []

        for asset in extracted_assets:
            # Detect MIME type if not provided
            mime_type = asset.mime_type or detect_mime_type(None, asset.url)

            # Create PageAsset
            page_asset = PageAsset(
                page_id=self.page_id,
                asset_type=asset.asset_type,
                url=asset.url,
                mime_type=mime_type,
            )

            saved_asset = await self.repository.create(page_asset)
            saved_assets.append(saved_asset)

        return saved_assets
