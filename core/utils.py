"""
core/utils.py
-------------
Genel async ve HTTP yardımcı fonksiyonları.
"""
import asyncio
from typing import Coroutine, Any
from fastapi import Request


async def run_with_disconnect_check(request: Request, coro: Coroutine) -> Any:
    """İstemci bağlantısının kesilip kesilmediğini izlerken bir coroutine çalıştırır.
    İstemci bağlantıyı keserse coroutine görevi derhal iptal edilir.
    """
    task = asyncio.create_task(coro)

    async def check_disconnect():
        while True:
            if await request.is_disconnected():
                task.cancel()
                return
            await asyncio.sleep(0.1)

    checker = asyncio.create_task(check_disconnect())
    try:
        return await task
    finally:
        checker.cancel()
