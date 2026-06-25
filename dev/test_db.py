import asyncio
import asyncpg
import json

async def main():
    conn = await asyncpg.connect('postgresql://router_user:router_pass@localhost:5433/orion_router')
    rows = await conn.fetch("SELECT id, request_json::text as req, response_json::text as res FROM router_request_logs ORDER BY id DESC LIMIT 5")
    for r in rows:
        print(f'=== ID: {r["id"]} ===')
        print(f'REQ: {r["req"]}')
        print(f'RES: {r["res"]}')
    await conn.close()

asyncio.run(main())
