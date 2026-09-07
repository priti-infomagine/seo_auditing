"""
Backward compatibility: schemas.resource_schema → models.resource_data
"""
from app.modules.parser.models.resource_data import ResourceData

__all__ = ["ResourceData"]
