"""
main.py
-------
Orion Custom Service Router — uygulama giriş noktası.

Sorumluluklar:
  - FastAPI uygulamasını oluştur
  - StaticFiles'ı bağla
  - Router modüllerini include et
  - /health endpoint'ini tanımla
"""
import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from core.lifespan import lifespan
from api import admin, chat, embeddings, files, speech

# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("service-router")

# Uvicorn loglarını --log-level warning ile başlattığımızda erişim logları (access) da kapanır.
# Erişim loglarını tekrar açmak için manuel olarak INFO seviyesine çekiyoruz.
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

# ---------------------------------------------------------------------------
#  Uygulama
# ---------------------------------------------------------------------------
app = FastAPI(title="Orion Custom Service Router", lifespan=lifespan)

# Dashboard UI statik dosyaları
from core.config import DASHBOARD_OUT_DIR

_dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
_public_static_dir = os.path.join(_dashboard_dir, "public", "static")
_out_dashboard_dir = os.path.join(DASHBOARD_OUT_DIR, "dashboard")

_static_candidates = [
    os.path.join(_out_dashboard_dir, "static"),
    os.path.join(DASHBOARD_OUT_DIR, "static"),
    _public_static_dir,
]
_static_dir = next((p for p in _static_candidates if os.path.exists(p)), None)
if _static_dir:
    app.mount("/dashboard/static", StaticFiles(directory=_static_dir), name="dashboard_static")

# Next.js SPA assets mount
_next_candidates = [
    os.path.join(_out_dashboard_dir, "_next"),
    os.path.join(DASHBOARD_OUT_DIR, "_next"),
]
_next_dir = next((p for p in _next_candidates if os.path.exists(p)), None)
if _next_dir:
    app.mount("/dashboard/_next", StaticFiles(directory=_next_dir), name="dashboard_next")


# ---------------------------------------------------------------------------
#  Router'ları bağla
# ---------------------------------------------------------------------------
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(embeddings.router)
app.include_router(speech.router)
app.include_router(files.router)

# ---------------------------------------------------------------------------
#  Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard")


# ---------------------------------------------------------------------------
#  CLI entry (Docker CMD, local: python main.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    from core.config import ROUTER_HOST, ROUTER_PORT

    reload = os.getenv("UVICORN_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "main:app",
        host=ROUTER_HOST,
        port=int(ROUTER_PORT),
        log_level=os.getenv("UVICORN_LOG_LEVEL", "warning"),
        reload=reload,
        reload_dirs=["data"] if reload else None,
    )
