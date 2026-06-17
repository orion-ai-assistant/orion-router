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
import sys

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from core.lifespan import lifespan
from api import admin, chat, embeddings, files, speech

# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------
class ColouredFormatter(logging.Formatter):
    GREY = "\033[90m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD_RED = "\033[1;31m"
    RESET = "\033[0m"

    LEVEL_COLORS = {
        logging.DEBUG: GREY,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    def format(self, record):
        log_color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        levelname = f"{log_color}{record.levelname:<5}{self.RESET}"
        name = f"{self.CYAN}{record.name}{self.RESET}"
        message = record.getMessage()
        
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if message[-1:] != "\n":
                message = message + "\n"
            message = message + record.exc_text
        if record.stack_info:
            if message[-1:] != "\n":
                message = message + "\n"
            message = message + self.formatStack(record.stack_info)
            
        if os.path.exists("/.dockerenv"):
            return f"[{levelname}] {name}: {message}"
        else:
            asctime = self.formatTime(record, self.datefmt)
            return f"{self.GREY}{asctime}{self.RESET} [{levelname}] {name}: {message}"

if sys.platform == "win32":
    os.system("")  # Enable ANSI support on Windows

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColouredFormatter())
logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)
logger = logging.getLogger("service-router")

# Uvicorn loglarını --log-level warning ile başlattığımızda erişim logları (access) da kapanır.
# Erişim loglarını tekrar açmak için manuel olarak INFO seviyesine çekiyoruz.
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

class DockerLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if "Press CTRL+C to quit" in record.getMessage():
            return False
        return True

if os.path.exists("/.dockerenv"):
    logging.getLogger("uvicorn.error").addFilter(DockerLogFilter())
    logging.getLogger("uvicorn").addFilter(DockerLogFilter())

from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse

class LocalhostWarningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host", "")
        # Sadece API endpointleri için uyarı basıyoruz (Dashboard'un kendi içi iletişimini darlamamak için)
        if "localhost" in host and request.url.path.startswith("/v1/"):
            logger.warning(f"Performans Engeli: İstemci '{host}' üzerinden bağlandı. İstek 400 hatası ile reddedildi.")
            
            # Dil tercihine göre çeviriyi alıyoruz
            accept_lang = request.headers.get("accept-language")
            from bin.i18n import t_lang
            error_message = t_lang("api_err_localhost_not_allowed", accept_lang)
            
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "message": error_message,
                        "type": "invalid_request_error",
                        "code": "localhost_not_allowed"
                    }
                }
            )
            
        return await call_next(request)


# ---------------------------------------------------------------------------
#  Uygulama
# ---------------------------------------------------------------------------
app = FastAPI(title="Orion Custom Service Router", lifespan=lifespan)
app.add_middleware(LocalhostWarningMiddleware)

# CORS ayarları: frontend geliştirme sunucusunun (localhost:3001) API'ye doğrudan erişebilmesi için
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        reload=reload,
        reload_dirs=["data"] if reload else None,
        use_colors=True,
    )
