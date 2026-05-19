"""
실행 방법:
  python run.py

PyInstaller .exe 패키징 시 진입점으로 사용됩니다.
"""
import uvicorn
import webbrowser
import threading
import time
import os
import sys

PORT = 8002

def open_browser():
    time.sleep(1.5)  # 서버 뜰 때까지 대기
    webbrowser.open(f"http://localhost:{PORT}")

if __name__ == "__main__":
    # 브라우저 자동 실행
    threading.Thread(target=open_browser, daemon=True).start()

    # FastAPI 서버 실행
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=PORT,
        reload=False
    )
