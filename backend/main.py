from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.routers import claim, report, ai
import os

app = FastAPI(title="납품 불량 클레임 대응 자동화 시스템", version="1.0.0")

# 라우터 등록
app.include_router(claim.router)
app.include_router(report.router)
app.include_router(ai.router)

# 정적 파일 서빙 (HTML/CSS/JS + 업로드 이미지)
app.mount("/uploads", StaticFiles(directory="frontend/uploads"), name="uploads")
app.mount("/css", StaticFiles(directory="frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")


# 페이지 라우팅
@app.get("/")
def index():
    return FileResponse("frontend/index.html")

@app.get("/list")
def list_page():
    return FileResponse("frontend/list.html")

@app.get("/search")
def search_page():
    return FileResponse("frontend/search.html")
