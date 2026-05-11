import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import claim, ai, auth
from backend.models.database import init_db

logging.basicConfig(level=logging.INFO)

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

