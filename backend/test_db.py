# test_db.py
import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

async def test_connection():
    try:
        # Get the database URL from environment
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("DATABASE_URL not found in environment variables")
            return

        # Parse the URL to get connection parameters
        parsed = urlparse(db_url)
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 5432
        database = parsed.path[1:]  # Remove leading slash
        
        print(f"Attempting to connect to database at {host}...")
        conn = await asyncpg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl='require'  # Required for Render.com
        )
        print("Successfully connected to the database!")
        await conn.close()
    except Exception as e:
        print(f"Failed to connect: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_connection())