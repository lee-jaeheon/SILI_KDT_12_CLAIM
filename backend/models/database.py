import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "3306"))
DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME     = os.getenv("DB_NAME", "claims_db")


@contextmanager
def get_conn():
    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
                    description TEXT,
                    created_at  DATETIME     DEFAULT NOW()
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
                    claim_text           TEXT,
                    extracted_text       TEXT,
                    claim_summary        TEXT,
                    root_cause_analysis  TEXT,
                    corrective_action    TEXT,
                    preventive_action    TEXT,
                    ai_defect_type       VARCHAR(50),
                    ai_confidence        FLOAT,
                    llm_model            VARCHAR(100),
                    llm_extraction_json  JSON,
                    handler              VARCHAR(100),
                    author_name          VARCHAR(100),
                    reviewer_name        VARCHAR(100),
                    approver_name        VARCHAR(100),
                    report_status        VARCHAR(20)  NOT NULL DEFAULT 'draft',
                    created_at           DATETIME     DEFAULT NOW(),
                    updated_at           DATETIME     DEFAULT NOW(),
                    FOREIGN KEY (defect_type) REFERENCES defect_types(code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS defect_report_images (
                    image_id            INT          PRIMARY KEY AUTO_INCREMENT,
                    report_id           INT          NOT NULL,
                    image_type          VARCHAR(100),
                    original_image_path VARCHAR(500),
                    image_path          VARCHAR(500) NOT NULL,
                    image_description   TEXT,
                    defect_bbox         JSON,
                    uploaded_at         DATETIME     DEFAULT NOW(),
                    FOREIGN KEY (report_id) REFERENCES defect_reports(report_id)
                        ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                INSERT IGNORE INTO defect_types (code, label, category_id, description) VALUES
                    ('OUTER_DAMAGE', '외관 손상', 102, '외관 긁힘, 찍힘, 변형 등 육안 식별 불량'),
                    ('SEALING',      '실링 불량', 204, '실링재 미도포, 부족, 위치 이탈'),
                    ('HEMMING',      '헤밍 불량', 212, '헤밍 공정 접합 불량'),
                    ('HOLE_DEFORM',  '홀 변형',   213, '홀 치수 이탈, 변형')
            """)


# ── defect_types ───────────────────────────────────────────────────────────────

def get_defect_types() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM defect_types")
            return cur.fetchall()


# ── defect_reports CRUD ────────────────────────────────────────────────────────

def _generate_document_no(conn) -> str:
    year = datetime.now().strftime("%Y")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(CAST(SUBSTR(document_no, 10) AS UNSIGNED)) AS max_seq "
            "FROM defect_reports WHERE document_no LIKE %s",
            (f"CLM-{year}-%",)
        )
        row = cur.fetchone()
    seq = (row["max_seq"] or 0) + 1
    return f"CLM-{year}-{seq:04d}"


def insert_report(
    customer_name: str,
    defect_type: str = None,
    defect_location: str = None,
    ai_defect_type: str = None,
    ai_confidence: float = None,
    llm_model: str = None,
    llm_extraction_json: dict = None,
    product_name: str = None,
    product_no: str = None,
    part_name: str = None,
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
) -> int:
    with get_conn() as conn:
        doc_no   = _generate_document_no(conn)
        received = datetime.now().strftime("%Y-%m-%d")
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO defect_reports (
                    document_no, received_date, customer_name,
                    defect_type, defect_location,
                    ai_defect_type, ai_confidence, llm_model, llm_extraction_json,
                    product_name, product_no, part_name, process_name, lot_no,
                    delivery_quantity, defect_quantity,
                    claim_text, extracted_text, claim_summary,
                    handler, author_name, delivery_date, issue_date
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (doc_no, received, customer_name,
                 defect_type, defect_location,
                 ai_defect_type, ai_confidence, llm_model,
                 json.dumps(llm_extraction_json, ensure_ascii=False) if llm_extraction_json else None,
                 product_name, product_no, part_name, process_name, lot_no,
                 delivery_quantity, defect_quantity,
                 claim_text, extracted_text, claim_summary,
                 handler, author_name, delivery_date, issue_date),
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
                    "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (status, limit, offset)
                )
            else:
                cur.execute(
                    "SELECT * FROM defect_reports ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (limit, offset)
                )
            items = cur.fetchall()

    return {"total": total, "items": items}


ALLOWED_UPDATE_FIELDS = {
    "defect_type", "defect_code", "defect_location",
    "product_name", "product_no", "part_name", "process_name", "lot_no",
    "customer_name", "delivery_quantity", "defect_quantity",
    "delivery_date", "issue_date",
    "claim_text", "extracted_text", "claim_summary",
    "root_cause_analysis", "corrective_action", "preventive_action",
    "handler", "author_name", "reviewer_name", "approver_name",
    "report_status", "llm_model",
}

def update_report(report_id: int, fields: dict) -> bool:
    update = {k: v for k, v in fields.items() if k in ALLOWED_UPDATE_FIELDS}
    if not update:
        return False
    update["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols = ", ".join(f"{k}=%s" for k in update)
    vals = list(update.values()) + [report_id]
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE defect_reports SET {cols} WHERE report_id = %s", vals)
            return cur.rowcount > 0


def delete_report(report_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM defect_report_images WHERE report_id = %s", (report_id,)
            )
            rows = cur.fetchall()
            cur.execute("DELETE FROM defect_reports WHERE report_id = %s", (report_id,))
    for row in rows:
        full_path = Path(__file__).parent.parent.parent / row["image_path"].lstrip("/")
        if full_path.exists():
            full_path.unlink()


# ── defect_report_images ───────────────────────────────────────────────────────

def insert_image(
    report_id: int,
    image_path: str,
    image_type: str = None,
    image_description: str = None,
    original_image_path: str = None,
    defect_bbox: list = None,
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO defect_report_images
                   (report_id, image_type, image_path, image_description,
                    original_image_path, defect_bbox)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (report_id, image_type, image_path, image_description,
                 original_image_path,
                 json.dumps(defect_bbox) if defect_bbox else None),
            )
            return cur.lastrowid


def get_images(report_id: int) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM defect_report_images WHERE report_id = %s", (report_id,))
            return cur.fetchall()


def delete_image(image_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT image_path FROM defect_report_images WHERE image_id = %s", (image_id,)
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM defect_report_images WHERE image_id = %s", (image_id,))
    if row:
        full_path = Path(__file__).parent.parent.parent / row["image_path"].lstrip("/")
        if full_path.exists():
            full_path.unlink()


# ── 유사 사례 검색 ──────────────────────────────────────────────────────────────

def search_similar(defect_type: str, customer_name: str = None, limit: int = 5) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM (
                    SELECT *, 2 AS score FROM defect_reports
                    WHERE report_status = 'approved' AND defect_type = %s AND customer_name = %s
                    UNION ALL
                    SELECT *, 1 AS score FROM defect_reports
                    WHERE report_status = 'approved' AND defect_type = %s
                      AND (%s IS NULL OR customer_name != %s)
                ) AS t ORDER BY score DESC, created_at DESC LIMIT %s""",
                (defect_type, customer_name or "", defect_type, customer_name, customer_name or "", limit),
            )
            return cur.fetchall()
