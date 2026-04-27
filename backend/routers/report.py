from fastapi import APIRouter, Query
from backend.models.database import get_db

router = APIRouter(prefix="/report", tags=["report"])


@router.get("/similar")
def get_similar_cases(defect_type: str = Query(...), supplier: str = Query(None)):
    """유사 클레임 사례 검색 → 보고서 초안 재료"""
    db = get_db()

    # 같은 불량 유형 + 같은 납품처 우선, 없으면 불량 유형만 매칭
    if supplier:
        rows = db.execute("""
            SELECT * FROM claims
            WHERE defect_type = ? AND supplier = ?
            ORDER BY created_at DESC LIMIT 5
        """, (defect_type, supplier)).fetchall()
    else:
        rows = []

    if not rows:
        rows = db.execute("""
            SELECT * FROM claims
            WHERE defect_type = ?
            ORDER BY created_at DESC LIMIT 5
        """, (defect_type,)).fetchall()

    db.close()
    results = [dict(row) for row in rows]

    # 가장 최근 사례로 보고서 초안 생성
    draft = None
    if results:
        latest = results[0]
        draft = {
            "cause_code": latest["cause_code"],
            "action": latest["action"],
            "source_id": latest["id"],
            "source_supplier": latest["supplier"],
        }

    return {"similar_cases": results, "draft": draft}
