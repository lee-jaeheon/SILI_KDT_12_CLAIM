"""
DB 초기화 스크립트
처음 세팅할 때 한 번만 실행하면 됩니다.
: python init_db.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "claims.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 클레임 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            supplier TEXT NOT NULL,           -- 납품처
            defect_type TEXT NOT NULL,        -- 불량 유형 (확정)
            ai_suggestion TEXT,               -- AI 제안 유형
            cause_code TEXT,                  -- 원인 코드
            action TEXT,                      -- 대책 문구
            handler TEXT,                     -- 담당자 이름
            image_path TEXT,                  -- 불량 사진 경로
            memo TEXT,                        -- 메모
            status TEXT DEFAULT '접수'        -- 접수 / 처리중 / 완료
        )
    """)

    # 샘플 데이터 (시연용)
    sample_data = [
        ("현대부품", "스크래치", "스크래치", "M01", "연마 공정 조건 재설정 및 작업자 교육 실시", "홍길동", None, "표면 스크래치 다수 발생"),
        ("기아모터스", "이물·오염", "이물·오염", "M03", "작업 환경 청결 유지 및 이물 유입 차단 조치", "김철수", None, "이물질 혼입"),
        ("현대부품", "스크래치", "스크래치", "M01", "연마 공정 조건 재설정", "홍길동", None, "동일 불량 재발"),
        ("삼성전자", "치수불량", "치수불량", "M05", "금형 점검 및 치수 재측정 후 조정", "이영희", None, "규격 초과"),
        ("기아모터스", "찍힘·변형", "찍힘·변형", "M02", "취급 주의 교육 및 포장 방법 개선", "김철수", None, "운반 중 변형 발생"),
    ]

    cursor.executemany("""
        INSERT INTO claims (supplier, defect_type, ai_suggestion, cause_code, action, handler, image_path, memo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_data)

    conn.commit()
    conn.close()
    print(f"✅ DB 초기화 완료: {DB_PATH}")
    print(f"✅ 샘플 데이터 {len(sample_data)}건 삽입 완료")

if __name__ == "__main__":
    init_db()
