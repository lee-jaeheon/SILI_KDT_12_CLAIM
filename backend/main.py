import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import claim, ai, auth
from backend.models.database import init_db, get_conn
from backend.ai.ollama import OLLAMA_URL, OLLAMA_MODEL

_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_file_handler = RotatingFileHandler(
    _LOG_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])

app = FastAPI(title="납품 불량 클레임 대응 자동화 시스템", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(claim.router)
app.include_router(ai.router)

_BASE = Path(__file__).parent.parent
(_BASE / "uploads").mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_BASE / "uploads")),        name="uploads")
app.mount("/css",     StaticFiles(directory=str(_BASE / "frontend" / "css")),   name="css")
app.mount("/js",      StaticFiles(directory=str(_BASE / "frontend" / "js")),    name="js")
app.mount("/fonts",   StaticFiles(directory=str(_BASE / "frontend" / "fonts")), name="fonts")


@app.on_event("startup")
async def startup():
    init_db()


MODEL_PATH = _BASE / "models" / "defect_classifier.pt"


@app.get("/health")
async def health():
    # 내부 오류 메시지·전체 경로 노출 방지. ok 여부만 외부 공개.
    checks = {}

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        checks["db"] = {"ok": True}
    except Exception as e:
        logging.warning("health: DB check failed: %s", e)
        checks["db"] = {"ok": False}

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            res = await client.get(OLLAMA_URL.replace("/api/generate", "/api/tags"))
            res.raise_for_status()
            tags = res.json().get("models", [])
            names = [t.get("name", "") for t in tags]
            checks["ollama"] = {"ok": True, "model_loaded": OLLAMA_MODEL in names}
    except Exception as e:
        logging.warning("health: Ollama check failed: %s", e)
        checks["ollama"] = {"ok": False}

    checks["model"] = {"ok": MODEL_PATH.exists()}

    overall = all(c.get("ok") for c in checks.values())
    return JSONResponse(
        status_code=200 if overall else 503,
        content={"status": "ok" if overall else "degraded", "checks": checks},
    )


@app.get("/")
def index():
    return FileResponse(str(_BASE / "frontend" / "index.html"))

@app.get("/hub")
def hub_page():
    return FileResponse(str(_BASE / "frontend" / "hub.html"))

@app.get("/list")
def list_page():
    return FileResponse(str(_BASE / "frontend" / "list.html"))

@app.get("/claim")
def claim_page():
    return FileResponse(str(_BASE / "frontend" / "claim_step1.html"))

@app.get("/claim-step2")
def claim_step2_page():
    return FileResponse(str(_BASE / "frontend" / "claim_step2.html"))

@app.get("/claim-step3")
def claim_step3_page():
    return FileResponse(str(_BASE / "frontend" / "report-download.html"))

@app.get("/cases")
def cases_page():
    return FileResponse(str(_BASE / "frontend" / "cases.html"))

@app.get("/admin")
def admin_page():
    return FileResponse(str(_BASE / "frontend" / "admin.html"))

@app.get("/logo.png")
def logo():
    return FileResponse(str(_BASE / "frontend" / "logo.png"))

