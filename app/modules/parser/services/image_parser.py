"""
Backward compatibility: ImageParser → ImageExtractor
"""
from app.modules.parser.extractors.image_extractor import ImageExtractor

ImageParser = ImageExtractor

__all__ = ["ImageParser", "ImageExtractor"]
