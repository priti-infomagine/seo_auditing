"""
Backward compatibility: schemas.image_schema → models.image_data
"""
from app.modules.parser.models.image_data import ImageData

ImageSchema = ImageData

__all__ = ["ImageSchema", "ImageData"]
