"""
Backward compatibility: schemas.link_schema → models.link_data
"""
from app.modules.parser.models.link_data import LinkData

LinkSchema = LinkData

__all__ = ["LinkData", "LinkSchema"]
