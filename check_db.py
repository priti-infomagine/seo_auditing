import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        database="seo_audit",
        user="postgres",
        password="vksoft123"
    )
    cursor = conn.cursor()
    
    # Check if sitemap_checks table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'sitemap_checks'
        )
    """)
    exists = cursor.fetchone()[0]
    print(f"sitemap_checks table exists: {exists}")
    
    if exists:
        # Get column info
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'sitemap_checks'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        print("\nColumns in sitemap_checks:")
        for col in columns:
            print(f"  {col[0]}: {col[1]} (nullable={col[2]}, default={col[3]})")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
