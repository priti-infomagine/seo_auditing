"""
Backward compatibility: schemas.technical_schema → models.technical_data
"""
from app.modules.parser.models.technical_data import TechnicalData

TechnicalSchema = TechnicalData

__all__ = ["TechnicalSchema", "TechnicalData"]
