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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at    TEXT DEFAULT (datetime('now', 'localtime')),

            -- 기본 정보
            doc_number    TEXT,                  -- 문서번호 (예: NCR-2026-001)
            issued_date   TEXT,                  -- 발행일
            customer      TEXT NOT NULL,         -- 고객사 (납품처)
            delivery_date TEXT,                  -- 납품일
            delivery_qty  INTEGER,               -- 납품수량
            part_name     TEXT,                  -- 품명/품번
            defect_qty    INTEGER,               -- 불량수량

            -- 불량 정보
            defect_type   TEXT NOT NULL,         -- 불량 유형 (확정)
            ai_suggestion TEXT,                  -- AI 제안 유형

            -- 대응 내용
            cause         TEXT,                  -- 원인분석
            action        TEXT,                  -- 시정조치
            prevention    TEXT,                  -- 예방대책

            -- 담당자 및 파일
            handler       TEXT,                  -- 담당자 이름
            image_path    TEXT,                  -- 불량 사진 경로
            report_path   TEXT,                  -- 생성된 보고서(.docx) 경로
            memo          TEXT,                  -- 메모

            -- 상태
            status        TEXT DEFAULT '접수'    -- 접수 / 처리중 / 완료
        )
    """)

    # 샘플 데이터 (시연용)
    sample_data = [
        ("NCR-2026-001", "2026-04-27", "현대부품",   "2026-04-25", 500, "엔진 커버 패널 A-001", 3,  "외관손상", "외관손상", "연마 공정 후 이송 중 접촉으로 표면 손상 발생", "연마 공정 조건 재설정 및 작업자 교육 실시", "이송 시 보호재 삽입 및 작업 표준서 개정", "홍길동", None, None, "표면 외관손상 다수 발생"),
        ("NCR-2026-002", "2026-04-25", "기아모터스", "2026-04-23", 300, "도어 프레임 B-002",    2,  "실링 불량", "실링 불량", "작업 환경 오염으로 실링재 이물 혼입",         "작업 환경 청결 유지 및 이물 유입 차단 조치", "정기 청소 주기 단축 및 방진 설비 점검",     "김철수", None, None, "이물질 혼입"),
        ("NCR-2026-003", "2026-04-24", "현대부품",   "2026-04-22", 200, "엔진 커버 패널 A-001", 1,  "외관손상", "외관손상", "동일 공정 재발로 연마 조건 미준수 확인",       "연마 공정 조건 재설정",                      "공정 체크리스트 강화 및 작업자 재교육",      "홍길동", None, None, "동일 불량 재발"),
        ("NCR-2026-004", "2026-04-22", "삼성전자",   "2026-04-20", 100, "브라켓 C-003",         2,  "홀 변형", "홀 변형",  "금형 마모로 인한 홀 치수 규격 초과",           "금형 점검 및 치수 재측정 후 조정",           "금형 정기 점검 주기 단축",                   "이영희", None, None, "규격 초과"),
        ("NCR-2026-005", "2026-04-20", "기아모터스", "2026-04-18", 400, "도어 프레임 B-002",    3,  "헤밍 불량", "헤밍 불량", "운반 중 충격으로 헤밍부 변형 발생",           "취급 주의 교육 및 포장 방법 개선",           "완충재 추가 및 운반 절차 표준화",            "김철수", None, None, "운반 중 변형 발생"),
    ]

    cursor.executemany("""
        INSERT INTO claims (
            doc_number, issued_date, customer, delivery_date, delivery_qty,
            part_name, defect_qty, defect_type, ai_suggestion,
            cause, action, prevention, handler, image_path, report_path, memo
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_data)

    conn.commit()
    conn.close()
    print(f"✅ DB 초기화 완료: {DB_PATH}")
    print(f"✅ 샘플 데이터 {len(sample_data)}건 삽입 완료")

if __name__ == "__main__":
    init_db()
