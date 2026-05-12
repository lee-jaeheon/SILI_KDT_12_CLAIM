"""
DB 초기화 스크립트 — 처음 세팅할 때 한 번만 실행
사용법: python init_db.py
"""
from backend.models.database import init_db

if __name__ == "__main__":
    init_db()
    print("DB 초기화 완료")
