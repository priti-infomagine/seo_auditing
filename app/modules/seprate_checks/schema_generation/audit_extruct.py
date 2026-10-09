import httpx
import extruct
from fastapi import HTTPException

@app.get("/api/schema/audit")
async def audit_site_schema(url: str):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"User-Agent": "SEOAuditBot/1.0"})

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch the targeted website.")

        # Extruct parses Microdata, JSON-LD, OpenGraph, etc. out of the HTML
        extracted_data = extruct.extract(response.text, base_url=url, syntaxes=['jsonld'])

        json_ld_blocks = extracted_data.get('jsonld', [])

        return {
            "url": url,
            "has_schema": len(json_ld_blocks) > 0,
            "schema_count": len(json_ld_blocks),
            "detected_schemas": json_ld_blocks
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")
