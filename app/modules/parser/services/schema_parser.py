"""Schema Parser - Extracts structured data and schema.org markup."""
from typing import Dict, Any, List
import json
from bs4 import BeautifulSoup


class SchemaParser:
    """Extracts structured data and website schema markup."""
    
    @staticmethod
    def get_schema_markup(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """
        Extract all schema.org markup from page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of schema markup dictionaries
        """
        schemas = []
        
        # Find JSON-LD structured data
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                schema_data = json.loads(script.string)
                schemas.append({
                    "type": "json-ld",
                    "data": schema_data
                })
            except (json.JSONDecodeError, AttributeError):
                continue
        
        # Find microdata (itemscope, itemtype attributes)
        microdata_elements = soup.find_all(attrs={'itemscope': True})
        for element in microdata_elements:
            itemtype = element.get('itemtype', '')
            if itemtype and 'schema.org' in itemtype:
                schemas.append({
                    "type": "microdata",
                    "itemtype": itemtype,
                    "element": element.name
                })
        
        # Find RDFa (typeof attribute)
        rdfa_elements = soup.find_all(attrs={'typeof': True})
        for element in rdfa_elements:
            typeof = element.get('typeof', '')
            if typeof:
                schemas.append({
                    "type": "rdfa",
                    "typeof": typeof,
                    "element": element.name
                })
        
        return schemas
    
    @staticmethod
    def has_schema_markup(soup: BeautifulSoup) -> bool:
        """
        Check if page has any schema markup.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            True if schema markup found
        """
        return len(SchemaParser.get_schema_markup(soup)) > 0
    
    @staticmethod
    def get_schema_types(soup: BeautifulSoup) -> List[str]:
        """
        Extract schema.org types used on page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            List of schema types
        """
        schema_types = []
        schemas = SchemaParser.get_schema_markup(soup)
        
        for schema in schemas:
            if schema.get('type') == 'json-ld':
                data = schema.get('data', {})
                if isinstance(data, dict):
                    schema_type = data.get('@type', '')
                    if schema_type:
                        schema_types.append(schema_type)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            schema_type = item.get('@type', '')
                            if schema_type:
                                schema_types.append(schema_type)
            elif schema.get('type') in ['microdata', 'rdfa']:
                schema_type = schema.get('itemtype', '') or schema.get('typeof', '')
                if schema_type:
                    # Extract type from URL
                    if 'schema.org/' in schema_type:
                        schema_type = schema_type.split('schema.org/')[-1]
                    schema_types.append(schema_type)
        
        return list(set(schema_types))  # Remove duplicates
    
    @staticmethod
    def validate_schema(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Validate schema markup on page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Validation results
        """
        schemas = SchemaParser.get_schema_markup(soup)
        schema_types = SchemaParser.get_schema_types(soup)
        
        issues = []
        warnings = []
        
        if not schemas:
            warnings.append("No schema markup found")
        
        # Check for required properties based on common types
        for schema_type in schema_types:
            if schema_type.lower() in ['localbusiness', 'organization', 'person']:
                # These should have name, address
                pass  # Could add more detailed validation here
        
        return {
            "has_schema": len(schemas) > 0,
            "schema_count": len(schemas),
            "schema_types": schema_types,
            "issues": issues,
            "warnings": warnings,
            "valid": len(issues) == 0
        }