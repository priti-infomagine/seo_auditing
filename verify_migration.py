import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings

async def check():
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        # Count by scope
        result = await conn.execute(text("""
            SELECT scope, count(*) FROM url_ignore_patterns 
            WHERE record_type = 'pattern' GROUP BY scope ORDER BY scope
        """))
        for row in result:
            print(f'{row[0]}: {row[1]}')
        
        # Total patterns
        result = await conn.execute(text("SELECT count(*) FROM url_ignore_patterns WHERE record_type = 'pattern'"))
        print(f'Total patterns: {result.scalar()}')
        
        # Check crawl_jobs pages_skipped column
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'crawl_jobs' AND column_name = 'pages_skipped'"))
        print(f'pages_skipped column exists: {result.scalar() is not None}')
    
    await engine.dispose()

asyncio.run(check())