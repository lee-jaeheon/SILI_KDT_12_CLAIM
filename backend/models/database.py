import json
import logging
import os
import ast
import re
import threading
from contextlib import contextmanager
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger(__name__)

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "claims_db")
BASE_DIR    = Path(__file__).parent.parent.parent
SAMPLE_SQL_PATH = BASE_DIR / "sampleDBB.sql"


class ReportNotFoundError(Exception):
    """Raised when an image operation references a missing report."""


def _index_exists(cur, table_name: str, index_name: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.statistics
        WHERE table_schema = %s
          AND table_name = %s
          AND index_name = %s
        """,
        (DB_NAME, table_name, index_name),
    )
    return cur.fetchone()["cnt"] > 0


def _column_type(cur, table_name: str, column_name: str) -> str | None:
    cur.execute(
        """
        SELECT column_type AS col_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name = %s
        """,
        (DB_NAME, table_name, column_name),
    )
    row = cur.fetchone()
    return row["col_type"].lower() if row else None


def _ensure_index(cur, table_name: str, index_name: str, ddl: str):
    if not _index_exists(cur, table_name, index_name):
        cur.execute(ddl)


def _ensure_schema_extensions(cur):
    if _column_type(cur, "defect_reports", "claim_text") != "longtext":
        cur.execute("ALTER TABLE defect_reports MODIFY claim_text LONGTEXT")
    if _column_type(cur, "defect_reports", "extracted_text") != "longtext":
        cur.execute("ALTER TABLE defect_reports MODIFY extracted_text LONGTEXT")

    # part_category 컬럼 추가 (FRAME / CONNECTOR 구분)
    if _column_type(cur, "defect_reports", "part_category") is None:
        cur.execute(
            "ALTER TABLE defect_reports "
            "ADD COLUMN part_category VARCHAR(20) DEFAULT 'FRAME' AFTER part_name"
        )

    _ensure_index(
        cur,
        "defect_reports",
        "idx_reports_status_id",
        "CREATE INDEX idx_reports_status_id "
        "ON defect_reports (report_status, report_id)",
    )
    _ensure_index(
        cur,
        "defect_reports",
        "idx_reports_similar",
        "CREATE INDEX idx_reports_similar "
        "ON defect_reports (report_status, defect_type, customer_name, report_id)",
    )
    _ensure_index(
        cur,
        "defect_report_images",
        "idx_images_report",
        "CREATE INDEX idx_images_report "
        "ON defect_report_images (report_id)",
    )


def _seed_document_sequences(cur):
    cur.execute(
        """
        INSERT INTO document_sequences (seq_year, last_seq)
        SELECT
            CAST(SUBSTR(document_no, 5, 4) AS UNSIGNED) AS seq_year,
            MAX(CAST(SUBSTR(document_no, 10) AS UNSIGNED)) AS last_seq
        FROM defect_reports
        WHERE document_no REGEXP '^CLM-[0-9]{4}-[0-9]+$'
        GROUP BY CAST(SUBSTR(document_no, 5, 4) AS UNSIGNED)
        ON DUPLICATE KEY UPDATE
            last_seq = GREATEST(document_sequences.last_seq, VALUES(last_seq))
        """
    )


def _seed_defect_types(cur):
    from backend.core.defects import DEFECT_SEED
    cur.executemany(
        """
        INSERT IGNORE INTO defect_types (code, label, category_id, description)
        VALUES (%s, %s, %s, %s)
        """,
        DEFECT_SEED,
    )


def _extract_insert_rows(sql_text: str, table_name: str) -> list[tuple]:
    # 백틱 표기 우선, 없으면 일반 표기
    for marker in (f"INSERT INTO `{table_name}`", f"INSERT INTO {table_name}"):
        start = sql_text.find(marker)
        if start >= 0:
            break
    if start < 0:
        return []
    m = re.search(r'\bVALUES\b', sql_text[start:], re.IGNORECASE)
    if not m:
        return []
    after_values = start + m.end()
    values_start = sql_text.find("\n", after_values)
    if values_start < 0:
        return []
    values_start += 1
    end = sql_text.find(";\n", values_start)
    if end < 0:
        end = sql_text.find(";", values_start)
    if end < 0:
        return []
    values_text = sql_text[values_start:end].strip()
    if not values_text:
        return []
    # 단어 경계로 NULL만 치환 — 문자열 리터럴 내 'NULL' 포함 단어는 건드리지 않음
    values_text = re.sub(r'\bNULL\b', 'None', values_text)
    try:
        return list(ast.literal_eval(f"[{values_text}]"))
    except (SyntaxError, ValueError):
        return []


def _seed_admin_user(cur):
    """기본 계정 시드 (admin + 시연용 일반 유저 2명, 모두 비밀번호 1234)"""
    try:
        from passlib.context import CryptContext
        hashed = CryptContext(schemes=["bcrypt"], deprecated="auto").hash("1234")
    except ImportError:
        _logger.warning("passlib 미설치 — 계정 시드 건너뜀")
        return

    seed_users = [
        ("admin", hashed, "관리자", "admin"),
        ("qa01",  hashed, "김철수",  "user"),
        ("qa02",  hashed, "이영수",  "user"),
    ]
    for username, pw, name, role in seed_users:
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO users (username, password, name, role) VALUES (%s, %s, %s, %s)",
            (username, pw, name, role),
        )


def _seed_sample_cases(cur):
    if not SAMPLE_SQL_PATH.exists():
        return
    cur.execute("SELECT COUNT(1) AS cnt FROM defect_reports")
    if cur.fetchone()["cnt"] > 0:
        return

    try:
        sql_text = SAMPLE_SQL_PATH.read_text(encoding="utf-8")
        report_rows = _extract_insert_rows(sql_text, "defect_reports")
        image_rows = _extract_insert_rows(sql_text, "defect_report_images")

        if report_rows:
            cur.executemany(
                """
                INSERT IGNORE INTO defect_reports (
                    report_id, document_no, received_date, defect_type, defect_code,
                    defect_location, customer_name, product_name, product_no, part_name,
                    process_name, lot_no, delivery_quantity, claim_text, extracted_text,
                    claim_summary, root_cause_analysis, corrective_action,
                    preventive_action, handler, author_name, reviewer_name,
                    approver_name, report_status
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                """,
                [
                    (
                        row[0], row[1], row[2], row[4], row[5],
                        row[6], row[7], row[8], row[9], row[10],
                        row[11], row[12], row[13], row[14], row[15],
                        row[16], row[18], row[19],
                        row[20], row[21], row[22], row[23],
                        row[24], row[25],
                    )
                    for row in report_rows
                ],
            )

        if image_rows:
            cur.executemany(
                """
                INSERT IGNORE INTO defect_report_images (
                    image_id, report_id, image_type, image_path,
                    image_description, uploaded_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                image_rows,
            )
    except Exception as e:
        _logger.warning("샘플 데이터 로드 실패 (무시됨): %s", e)


def _seed_connector_cases(conn):
    """커넥터 불량 샘플 케이스 시드 — 커넥터 레코드가 없을 때만 삽입."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(1) AS cnt FROM defect_reports WHERE part_category = 'CONNECTOR'"
        )
        if cur.fetchone()["cnt"] > 0:
            return

    _CONNECTOR_SAMPLES = [
        {
            "customer_name": "현대모비스",
            "defect_type": "GAP_DEFECT",
            "part_category": "CONNECTOR",
            "defect_location": "커넥터 하우징 결합부",
            "product_name": "ABS 커넥터",
            "product_no": "CNT-ABS-001",
            "part_name": "커넥터",
            "delivery_quantity": 1000,
            "defect_quantity": 12,
            "handler": "김철수",
            "root_cause_analysis": "커넥터 하우징의 금형 마모로 인해 조립 시 간격이 규격(0.05mm)을 초과함. 생산 후 검사 공정에서 간격 게이지 미측정으로 유출.",
            "corrective_action": "금형 교체 및 간격 측정 게이지 추가 배치. 전수 검사 실시하여 불량품 격리 조치.",
            "preventive_action": "금형 수명 관리 대장 작성 및 500사이클마다 정기 점검 실시. 라인 출하 검사 기준서에 간격 측정 항목 추가.",
            "report_status": "approved",
        },
        {
            "customer_name": "기아",
            "defect_type": "FASTENING_DEFECT",
            "part_category": "CONNECTOR",
            "defect_location": "커넥터 잠금 클립",
            "product_name": "도어 와이어 커넥터",
            "product_no": "CNT-DW-007",
            "part_name": "커넥터",
            "delivery_quantity": 500,
            "defect_quantity": 5,
            "handler": "이영희",
            "root_cause_analysis": "조립 자동화 라인의 체결 토크 설정값이 최적값 대비 낮게 설정되어 잠금 클립이 완전 체결되지 않음. 진동 환경에서 클립이 분리될 위험 발생.",
            "corrective_action": "체결 토크를 표준값(2.5N·m)으로 재설정. 토크 모니터링 센서 알람 기준 강화. 해당 배치 전수 재검사.",
            "preventive_action": "자동화 라인 설비 파라미터 이력 관리 시스템 도입. 주간 1회 체결 토크 확인 절차 추가.",
            "report_status": "approved",
        },
        {
            "customer_name": "HLB모터스",
            "defect_type": "GAP_DEFECT",
            "part_category": "CONNECTOR",
            "defect_location": "핀 삽입부 간격",
            "product_name": "엔진 ECU 커넥터",
            "product_no": "CNT-ECU-003",
            "part_name": "커넥터",
            "delivery_quantity": 300,
            "defect_quantity": 3,
            "handler": "박민준",
            "root_cause_analysis": "핀 삽입 공정에서 작업자 수작업 오류 발생. 핀이 완전히 삽입되지 않아 규격(최소 삽입 깊이 8mm) 미달로 간격 불량 발생.",
            "corrective_action": "수작업 공정을 반자동 지그로 대체. 핀 삽입 후 통전 검사를 100% 실시.",
            "preventive_action": "작업자 교육 재실시. 핀 삽입 지그 도입 및 삽입 깊이 자동 감지 센서 설치.",
            "report_status": "submitted",
        },
        {
            "customer_name": "현대자동차",
            "defect_type": "FASTENING_DEFECT",
            "part_category": "CONNECTOR",
            "defect_location": "2차 잠금 장치",
            "product_name": "트랜스미션 커넥터",
            "product_no": "CNT-TM-012",
            "part_name": "커넥터",
            "delivery_quantity": 800,
            "defect_quantity": 8,
            "handler": "최정훈",
            "root_cause_analysis": "2차 잠금 장치의 플라스틱 래치 재료 물성 변화(충격 강도 저하)로 조립 시 파손. 원자재 입고 검사에서 물성 확인 누락.",
            "corrective_action": "해당 배치 원자재 전량 반품 조치. 물성이 확인된 대체 원자재로 교체 후 생산 재개.",
            "preventive_action": "원자재 입고 시 충격 강도 샘플 시험 의무화. 공급사 품질 협약서에 물성 성적서 첨부 조항 추가.",
            "report_status": "approved",
        },
        {
            "customer_name": "성우하이텍",
            "defect_type": "OUTER_DAMAGE",
            "part_category": "CONNECTOR",
            "defect_location": "커넥터 외관",
            "product_name": "배터리 커넥터",
            "product_no": "CNT-BAT-005",
            "part_name": "커넥터",
            "delivery_quantity": 200,
            "defect_quantity": 4,
            "handler": "강지은",
            "root_cause_analysis": "포장 불량으로 인해 운반 중 커넥터 외관이 손상됨. 완충재 규격이 커넥터 크기에 맞지 않아 유격 발생.",
            "corrective_action": "포장 방식 개선 — 개별 비닐 포장 후 에어캡 완충재 적용. 손상품 전량 폐기.",
            "preventive_action": "포장 설계서 업데이트 및 포장 검증 절차 추가. 수입 검사 시 포장 상태 확인 항목 신설.",
            "report_status": "submitted",
        },
    ]

    try:
        for s in _CONNECTOR_SAMPLES:
            doc_no = _generate_document_no(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO defect_reports (
                        document_no, defect_type, part_category, defect_location,
                        customer_name, product_name, product_no, part_name,
                        delivery_quantity, defect_quantity, handler,
                        root_cause_analysis, corrective_action, preventive_action,
                        report_status, received_date
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, CURDATE()
                    )
                    """,
                    (
                        doc_no,
                        s["defect_type"], s["part_category"], s["defect_location"],
                        s["customer_name"], s["product_name"], s["product_no"], s["part_name"],
                        s["delivery_quantity"], s["defect_quantity"], s["handler"],
                        s["root_cause_analysis"], s["corrective_action"], s["preventive_action"],
                        s["report_status"],
                    ),
                )
            conn.commit()
        _logger.info("커넥터 샘플 케이스 %d건 시드 완료", len(_CONNECTOR_SAMPLES))
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        _logger.warning("커넥터 샘플 시드 실패 (무시됨): %s", e)


_pool_lock = threading.Lock()
_pool: list = []
_POOL_MAX   = 10


def _create_raw_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
        autocommit=False,
    )


def _acquire():
    with _pool_lock:
        while _pool:
            conn = _pool.pop()
            try:
                conn.ping(reconnect=True)
                return conn
            except Exception:
                pass
    return _create_raw_conn()


def _release(conn):
    with _pool_lock:
        if len(_pool) < _POOL_MAX:
            _pool.append(conn)
            return
    try:
        conn.close()
    except Exception:
        pass


@contextmanager
def get_conn():
    conn = _acquire()
    ok = False
    try:
        yield conn
        conn.commit()
        ok = True
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if ok:
            _release(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


def init_db():
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        charset="utf8mb4",
    )
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    conn.commit()
    conn.close()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS defect_types (
                    code        VARCHAR(50)  PRIMARY KEY,
                    label       VARCHAR(100) NOT NULL,
                    category_id INT,
                    description TEXT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS document_sequences (
                    seq_year INT PRIMARY KEY,
                    last_seq INT NOT NULL DEFAULT 0
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS defect_reports (
                    report_id            INT          PRIMARY KEY AUTO_INCREMENT,
                    document_no          VARCHAR(20)  UNIQUE,
                    issue_date           DATE,
                    delivery_date        DATE,
                    received_date        DATE,
                    defect_type          VARCHAR(50),
                    defect_code          VARCHAR(50),
                    defect_location      VARCHAR(200),
                    customer_name        VARCHAR(200) NOT NULL,
                    product_name         VARCHAR(200),
                    product_no           VARCHAR(100),
                    part_name            VARCHAR(200),
                    process_name         VARCHAR(200),
                    lot_no               VARCHAR(100),
                    delivery_quantity    INT,
                    defect_quantity      INT,
                    claim_text           LONGTEXT,
                    extracted_text       LONGTEXT,
                    claim_summary        TEXT,
                    root_cause_analysis  TEXT,
                    corrective_action    TEXT,
                    preventive_action    TEXT,
                    ai_defect_type       VARCHAR(50),
                    ai_confidence        FLOAT,
                    llm_model            VARCHAR(100),
                    handler              VARCHAR(100),
                    author_name          VARCHAR(100),
                    reviewer_name        VARCHAR(100),
                    approver_name        VARCHAR(100),
                    report_status        VARCHAR(20)  NOT NULL DEFAULT 'draft',
                    FOREIGN KEY (defect_type) REFERENCES defect_types(code),
                    INDEX idx_reports_status_id (report_status, report_id),
                    INDEX idx_reports_similar (report_status, defect_type, customer_name, report_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS defect_report_images (
                    image_id            INT          PRIMARY KEY AUTO_INCREMENT,
                    report_id           INT          NOT NULL,
                    image_type          VARCHAR(100),
                    image_path          VARCHAR(500) NOT NULL,
                    image_description   TEXT,
                    defect_bbox         JSON,
                    uploaded_at         DATETIME     DEFAULT NOW(),
                    FOREIGN KEY (report_id) REFERENCES defect_reports(report_id)
                        ON DELETE CASCADE,
                    INDEX idx_images_report (report_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id    INT          PRIMARY KEY AUTO_INCREMENT,
                    username   VARCHAR(50)  UNIQUE NOT NULL,
                    password   VARCHAR(255) NOT NULL,
                    name       VARCHAR(100),
                    role       VARCHAR(20)  NOT NULL DEFAULT 'user',
                    is_active  TINYINT      NOT NULL DEFAULT 1,
                    created_at DATETIME     DEFAULT NOW()
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key_name VARCHAR(100) PRIMARY KEY,
                    value    VARCHAR(255) NOT NULL DEFAULT ''
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            _seed_defect_types(cur)
            _seed_sample_cases(cur)
            _seed_document_sequences(cur)
            _seed_admin_user(cur)

    # DDL(ALTER TABLE)은 트랜잭션 밖 별도 커넥션에서 실행
    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_schema_extensions(cur)

    # 커넥터 샘플 케이스 — 별도 커넥션에서 실행 (트랜잭션 독립)
    with get_conn() as conn:
        _seed_connector_cases(conn)


# ── defect_types 조회 ────────────────────────────────

def get_defect_types() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM defect_types")
            return cur.fetchall()


# ── settings CRUD ────────────────────────────────

def get_setting(key: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key_name = %s", (key,))
            row = cur.fetchone()
            return row["value"] if row else None


def get_all_settings() -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT key_name, value FROM settings")
            return {row["key_name"]: row["value"] for row in cur.fetchall()}


def upsert_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO settings (key_name, value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE value = %s",
                (key, value, value),
            )


# ── defect_reports CRUD ──────────────────────────

def _generate_document_no(conn) -> str:
    year = int(datetime.now().strftime("%Y"))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_sequences (seq_year, last_seq)
            VALUES (%s, 0)
            ON DUPLICATE KEY UPDATE last_seq = last_seq
            """,
            (year,),
        )
        cur.execute(
            "SELECT last_seq FROM document_sequences WHERE seq_year = %s FOR UPDATE",
            (year,),
        )
        row = cur.fetchone()
        seq = row["last_seq"] + 1
        cur.execute(
            "UPDATE document_sequences SET last_seq = %s WHERE seq_year = %s",
            (seq, year),
        )
    return f"CLM-{year}-{seq:04d}"


def insert_report(
    customer_name: str,
    defect_type: str = None,
    defect_code: str = None,
    defect_location: str = None,
    ai_defect_type: str = None,
    ai_confidence: float = None,
    llm_model: str = None,
    product_name: str = None,
    product_no: str = None,
    part_name: str = None,
    part_category: str = "FRAME",
    process_name: str = None,
    lot_no: str = None,
    delivery_quantity: int = None,
    defect_quantity: int = None,
    claim_text: str = None,
    extracted_text: str = None,
    claim_summary: str = None,
    handler: str = None,
    author_name: str = None,
    delivery_date: str = None,
    issue_date: str = None,
    root_cause_analysis: str = None,
    corrective_action: str = None,
    preventive_action: str = None,
    reviewer_name: str = None,
    approver_name: str = None,
) -> int:
    with get_conn() as conn:
        # author_name이 없으면 handler 값으로 자동 설정
        if not author_name and handler:
            author_name = handler
        # settings 테이블에서 검토자/승인자 자동 적용 (명시적으로 전달된 경우엔 유지)
        if not reviewer_name or not approver_name:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key_name, value FROM settings "
                    "WHERE key_name IN ('reviewer_name', 'approver_name')"
                )
                for row in cur.fetchall():
                    if row["key_name"] == "reviewer_name" and not reviewer_name:
                        reviewer_name = row["value"] or None
                    elif row["key_name"] == "approver_name" and not approver_name:
                        approver_name = row["value"] or None

        doc_no   = _generate_document_no(conn)
        received = datetime.now().strftime("%Y-%m-%d")
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO defect_reports (
                    document_no, received_date, customer_name,
                    defect_type, defect_code, defect_location,
                    ai_defect_type, ai_confidence, llm_model,
                    product_name, product_no, part_name, part_category, process_name, lot_no,
                    delivery_quantity, defect_quantity,
                    claim_text, extracted_text, claim_summary,
                    handler, author_name, delivery_date, issue_date,
                    root_cause_analysis, corrective_action, preventive_action,
                    reviewer_name, approver_name
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (doc_no, received, customer_name,
                 defect_type, defect_code, defect_location,
                 ai_defect_type, ai_confidence, llm_model,
                 product_name, product_no, part_name, part_category or "FRAME", process_name, lot_no,
                 delivery_quantity, defect_quantity,
                 claim_text, extracted_text, claim_summary,
                 handler, author_name, delivery_date, issue_date,
                 root_cause_analysis, corrective_action, preventive_action,
                 reviewer_name, approver_name),
            )
            return cur.lastrowid


def get_report(report_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM defect_reports WHERE report_id = %s", (report_id,))
            report = cur.fetchone()
            if not report:
                return None
            cur.execute("SELECT * FROM defect_report_images WHERE report_id = %s", (report_id,))
            report["images"] = cur.fetchall()
    return report


def list_reports(status: str = None, limit: int = 20, offset: int = 0) -> dict:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM defect_reports WHERE report_status = %s",
                    (status,)
                )
            else:
                cur.execute("SELECT COUNT(*) AS total FROM defect_reports")
            total = cur.fetchone()["total"]

            if status:
                cur.execute(
                    "SELECT * FROM defect_reports WHERE report_status = %s "
                    "ORDER BY report_id DESC LIMIT %s OFFSET %s",
                    (status, limit, offset)
                )
            else:
                cur.execute(
                    "SELECT * FROM defect_reports ORDER BY report_id DESC LIMIT %s OFFSET %s",
                    (limit, offset)
                )
            items = cur.fetchall()

        if items:
            report_ids = [item["report_id"] for item in items]
            placeholders = ", ".join(["%s"] * len(report_ids))
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM defect_report_images WHERE report_id IN ({placeholders}) ORDER BY image_id",
                    report_ids,
                )
                images_by_report = {}
                for img in cur.fetchall():
                    images_by_report.setdefault(img["report_id"], []).append(img)
            for item in items:
                item["images"] = images_by_report.get(item["report_id"], [])

    return {"total": total, "items": items}


ALLOWED_UPDATE_FIELDS = {
    "defect_type", "defect_code", "defect_location",
    "product_name", "product_no", "part_name", "part_category", "process_name", "lot_no",
    "customer_name", "delivery_quantity", "defect_quantity",
    "delivery_date", "issue_date",
    "claim_text", "extracted_text", "claim_summary",
    "root_cause_analysis", "corrective_action", "preventive_action",
    "handler", "author_name", "reviewer_name", "approver_name",
    "report_status", "llm_model",
}

VALID_REPORT_STATUSES = {"draft", "submitted", "approved", "rejected"}


def update_report(report_id: int, fields: dict) -> str:
    update = {k: v for k, v in fields.items() if k in ALLOWED_UPDATE_FIELDS}
    if not update:
        return "no_fields"
    if "report_status" in update and update["report_status"] not in VALID_REPORT_STATUSES:
        return "invalid_status"
    cols = ", ".join(f"{k}=%s" for k in update)
    vals = list(update.values()) + [report_id]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE defect_reports SET {cols} WHERE report_id = %s", vals)
            if cur.rowcount > 0:
                return "updated"
            cur.execute("SELECT 1 FROM defect_reports WHERE report_id = %s", (report_id,))
            return "unchanged" if cur.fetchone() else "missing"


def delete_report(report_id: int) -> int:
    """삭제된 row 수 반환 (0이면 대상 없음)"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM defect_report_images WHERE report_id = %s", (report_id,)
            )
            rows = cur.fetchall()
            cur.execute("DELETE FROM defect_reports WHERE report_id = %s", (report_id,))
            affected = cur.rowcount
    for row in rows:
        full_path = Path(__file__).parent.parent.parent / row["image_path"].lstrip("/")
        if full_path.exists():
            full_path.unlink()
    return affected


# ── defect_report_images ───────────────────────

def insert_image(
    report_id: int,
    image_path: str,
    image_type: str = None,
    image_description: str = None,
    defect_bbox: list = None,
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM defect_reports WHERE report_id = %s", (report_id,))
            if not cur.fetchone():
                raise ReportNotFoundError(f"report_id not found: {report_id}")
            cur.execute(
                """INSERT INTO defect_report_images
                   (report_id, image_type, image_path, image_description, defect_bbox)
                   VALUES (%s, %s, %s, %s, %s)""",
                (report_id, image_type, image_path, image_description,
                 json.dumps(defect_bbox) if defect_bbox else None),
            )
            return cur.lastrowid


def get_images(report_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM defect_report_images WHERE report_id = %s", (report_id,))
            return cur.fetchall()


def delete_image(image_id: int) -> int:
    """삭제된 row 수 반환 (0이면 대상 없음)"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM defect_report_images WHERE image_id = %s", (image_id,)
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM defect_report_images WHERE image_id = %s", (image_id,))
            affected = cur.rowcount
    if row:
        full_path = Path(__file__).parent.parent.parent / row["image_path"].lstrip("/")
        if full_path.exists():
            full_path.unlink()
    return affected


# ── 유사 사례 검색 ──────────────────────────────

SIMILARITY_WEIGHTS = {
    "defect_type": 30,
    "product": 20,
    "defect_detail": 15,
    "root_cause": 12,
    "actions": 10,
    "customer": 8,
    "process": 5,
}


def _normalize_text(value) -> str:
    return " ".join(str(value or "").lower().split())


def _text_similarity(left, right) -> float:
    left_text = _normalize_text(left)
    right_text = _normalize_text(right)
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0
    if left_text in right_text or right_text in left_text:
        overlap = min(len(left_text), len(right_text)) / max(len(left_text), len(right_text))
        return min(1.0, 0.85 + (0.15 * overlap))
    return SequenceMatcher(None, left_text, right_text).ratio()


def _avg_similarities(pairs: list[tuple]) -> float:
    scores = [_text_similarity(left, right) for left, right in pairs if left]
    return sum(scores) / len(scores) if scores else 0.0


def _max_similarity(left_values: list, right_values: list) -> float:
    scores = [
        _text_similarity(left, right)
        for left in left_values if left
        for right in right_values if right
    ]
    return max(scores) if scores else 0.0


def _similarity_level(score: int) -> str:
    if score >= 80:
        return "유사 사례"
    if score >= 60:
        return "참고 사례"
    return "유사 사례 없음"


def _score_similar_case(target: dict, case: dict) -> tuple[int, dict]:
    details = {}
    active = {
        "defect_type": bool(target.get("defect_type")),
        "product": any(target.get(key) for key in ("product_name", "product_no", "part_name")),
        "defect_detail": any(target.get(key) for key in ("defect_location", "claim_text", "claim_summary")),
        "root_cause": bool(target.get("root_cause_analysis")),
        "actions": any(target.get(key) for key in ("corrective_action", "preventive_action")),
        "customer": bool(target.get("customer_name")),
        "process": bool(target.get("process_name")),
    }
    details["defect_type"] = (
        1.0 if target.get("defect_type") and target.get("defect_type") == case.get("defect_type") else 0.0
    )
    details["product"] = _avg_similarities([
        (target.get("product_name"), case.get("product_name")),
        (target.get("product_no"), case.get("product_no")),
        (target.get("part_name"), case.get("part_name")),
    ])
    details["defect_detail"] = _max_similarity(
        [target.get("defect_location"), target.get("claim_text"), target.get("claim_summary")],
        [case.get("defect_location"), case.get("claim_text"), case.get("claim_summary")],
    )
    details["root_cause"] = _text_similarity(target.get("root_cause_analysis"), case.get("root_cause_analysis"))
    details["actions"] = _avg_similarities([
        (target.get("corrective_action"), case.get("corrective_action")),
        (target.get("preventive_action"), case.get("preventive_action")),
    ])
    details["customer"] = _text_similarity(target.get("customer_name"), case.get("customer_name"))
    details["process"] = _text_similarity(target.get("process_name"), case.get("process_name"))

    active_weight = sum(SIMILARITY_WEIGHTS[key] for key, enabled in active.items() if enabled)
    raw_score = sum(
        details[key] * SIMILARITY_WEIGHTS[key]
        for key, enabled in active.items()
        if enabled
    )
    score = round((raw_score / active_weight) * 100) if active_weight else 0
    score_details = {
        key: {
            "score": round(details[key] * SIMILARITY_WEIGHTS[key]),
            "weight": SIMILARITY_WEIGHTS[key],
            "active": active[key],
        }
        for key in SIMILARITY_WEIGHTS
    }
    return score, score_details


def search_similar(
    defect_type: str = None,
    customer_name: str = None,
    product_name: str = None,
    product_no: str = None,
    part_name: str = None,
    process_name: str = None,
    defect_location: str = None,
    claim_text: str = None,
    claim_summary: str = None,
    root_cause_analysis: str = None,
    corrective_action: str = None,
    preventive_action: str = None,
    limit: int = 5,
    min_score: int = 60,
) -> list[dict]:
    target = {
        "defect_type": defect_type,
        "customer_name": customer_name,
        "product_name": product_name,
        "product_no": product_no,
        "part_name": part_name,
        "process_name": process_name,
        "defect_location": defect_location,
        "claim_text": claim_text,
        "claim_summary": claim_summary,
        "root_cause_analysis": root_cause_analysis,
        "corrective_action": corrective_action,
        "preventive_action": preventive_action,
    }
    fetch_limit = max(limit * 10, 50)

    # 1단계: 후보 케이스 조회 후 커넥션 즉시 반환
    with get_conn() as conn:
        with conn.cursor() as cur:
            if defect_type and customer_name:
                cur.execute(
                    """
                    SELECT * FROM defect_reports
                    WHERE report_status = 'approved'
                      AND defect_type = %s
                      AND customer_name = %s
                    ORDER BY report_id DESC
                    LIMIT %s
                    """,
                    (defect_type, customer_name, fetch_limit),
                )
                cases = cur.fetchall()
                if not cases:
                    cur.execute(
                        """
                        SELECT * FROM defect_reports
                        WHERE report_status = 'approved' AND defect_type = %s
                        ORDER BY report_id DESC
                        LIMIT %s
                        """,
                        (defect_type, fetch_limit),
                    )
                    cases = cur.fetchall()
            elif defect_type:
                cur.execute(
                    """
                    SELECT * FROM defect_reports
                    WHERE report_status = 'approved' AND defect_type = %s
                    ORDER BY report_id DESC
                    LIMIT %s
                    """,
                    (defect_type, fetch_limit),
                )
                cases = cur.fetchall()
            else:
                cur.execute(
                    """
                    SELECT * FROM defect_reports
                    WHERE report_status = 'approved'
                    ORDER BY report_id DESC
                    LIMIT %s
                    """,
                    (fetch_limit,),
                )
                cases = cur.fetchall()

    # 2단계: Python 측 스코어링 (커넥션 미점유)
    results = []
    for case in cases:
        score, score_details = _score_similar_case(target, case)
        if score < min_score:
            continue
        case["similarity_score"] = score
        case["similarity_level"] = _similarity_level(score)
        case["score_details"] = score_details
        results.append(case)

    results.sort(key=lambda item: (item["similarity_score"], item["report_id"]), reverse=True)
    selected = results[:limit]

    # 3단계: 선택된 케이스의 이미지 조회 (별도 커넥션)
    if selected:
        report_ids = [item["report_id"] for item in selected]
        placeholders = ", ".join(["%s"] * len(report_ids))
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT *
                    FROM defect_report_images
                    WHERE report_id IN ({placeholders})
                    ORDER BY image_id
                    """,
                    report_ids,
                )
                images_by_report = {}
                for image in cur.fetchall():
                    images_by_report.setdefault(image["report_id"], []).append(image)
        for item in selected:
            item["images"] = images_by_report.get(item["report_id"], [])

    return selected
