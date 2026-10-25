import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL is missing from backend/.env")

engine = create_engine(database_url, pool_pre_ping=True)

try:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database(), version()")
        )
        database_name, version = result.fetchone()

        print("Neon connection successful!")
        print("Database:", database_name)
        print("PostgreSQL:", version.split(",")[0])
finally:
    engine.dispose()
