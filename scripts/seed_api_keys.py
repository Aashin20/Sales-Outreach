"""
Seed script — creates initial API keys in the database.
Run once after first deployment.

Usage:
    python scripts/seed_api_keys.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.config import get_settings
from app.models.database import Base, ApiKey
from app.security.auth import generate_api_key_v2


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    keys_to_create = [
        {"name": "demo-key", "rate_limit": 60, "daily_limit": 10.0},
        {"name": "test-key", "rate_limit": 120, "daily_limit": 50.0},
    ]

    print("=" * 60)
    print("SEEDING API KEYS")
    print("=" * 60)
    print()
    print("⚠️  SAVE THESE KEYS — they are shown only once!")
    print()

    async with session_factory() as db:
        for key_config in keys_to_create:
            plaintext, key_hash, prefix = generate_api_key_v2()
            api_key = ApiKey(
                key_hash=key_hash,
                key_prefix=prefix,
                name=key_config["name"],
                rate_limit_per_minute=key_config["rate_limit"],
                daily_cost_limit_usd=key_config["daily_limit"],
            )
            db.add(api_key)
            await db.commit()
            await db.refresh(api_key)

            print(f"  Name:      {key_config['name']}")
            print(f"  Key:       {plaintext}")
            print(f"  Key ID:    {api_key.id}")
            print(f"  Prefix:    {prefix}")
            print(f"  Rate:      {key_config['rate_limit']}/min")
            print(f"  Budget:    ${key_config['daily_limit']:.2f}/day")
            print()

    await engine.dispose()
    print("✅ Done! Use the keys above in your X-API-Key header.")


if __name__ == "__main__":
    asyncio.run(seed())
