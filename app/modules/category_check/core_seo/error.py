@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    e = exc.errors()[0]
    return JSONResponse(status_code=422, content={
        "error": {"code": e["type"].upper(), "field": str(e["loc"][-1]), "message": e["msg"]}
    })