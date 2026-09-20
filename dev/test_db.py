import asyncio
from database import db_manager

async def main():
    await db_manager.init_db()
    rows = await db_manager.fetch("SELECT name, provider, capability, is_active FROM router_models WHERE provider = 'local' ORDER BY capability")
    print("Local Models in DB:")
    for r in rows:
        print(f"  Capability: {r['capability']:<6} | Name: {r['name']:<12} | Active: {r['is_active']}")

asyncio.run(main())
