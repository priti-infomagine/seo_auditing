from fastapi import APIRouter, HTTPException, Query
import httpx
import extruct

router = APIRouter()


@router.get(
    "/audit",
    summary="Audit existing schema markup on a URL (GET)",
    description="Fetch a URL and extract all JSON-LD schema markup using extruct. Returns detected schemas with their types and properties.",
)
async def audit_site_schema(url: str = Query(..., description="URL to audit for schema markup")):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers={"User-Agent": "SEOAuditBot/1.0"}, follow_redirects=True)

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Could not fetch the targeted website: HTTP {response.status_code}")

        extracted = extruct.extract(response.text, base_url=url, syntaxes=["json-ld"])
        json_ld_blocks = extracted.get("json-ld", [])

        return {
            "url": url,
            "has_schema": len(json_ld_blocks) > 0,
            "schema_count": len(json_ld_blocks),
            "detected_schemas": json_ld_blocks,
        }

    except httpx.TimeoutException as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")