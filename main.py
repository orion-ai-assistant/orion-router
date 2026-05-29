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
_dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
if os.path.exists(_dashboard_dir):
    app.mount("/dashboard/static", StaticFiles(directory=_dashboard_dir), name="dashboard_static")
    
    # Next.js SPA assets mount
    _next_dir = os.path.join(_dashboard_dir, "out", "_next")
    if os.path.exists(_next_dir):
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
