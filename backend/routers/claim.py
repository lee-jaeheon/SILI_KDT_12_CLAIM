from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse
from backend.models.database import get_db
import shutil, os, uuid

router = APIRouter(prefix="/claims", tags=["claims"])

UPLOAD_DIR = "frontend/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.get("/")
def get_claims():
    """클레임 전체 목록 조회"""
    db = get_db()
    rows = db.execute("SELECT * FROM claims ORDER BY created_at DESC").fetchall()
    db.close()
    return [dict(row) for row in rows]


@router.get("/{claim_id}")
def get_claim(claim_id: int):
    """클레임 단건 조회"""
    db = get_db()
    row = db.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    db.close()
    if not row:
        return JSONResponse(status_code=404, content={"message": "클레임을 찾을 수 없습니다."})
    return dict(row)


@router.post("/")
async def create_claim(
    supplier: str = Form(...),
    defect_type: str = Form(...),
    ai_suggestion: str = Form(None),
    cause_code: str = Form(None),
    action: str = Form(None),
    handler: str = Form(...),
    memo: str = Form(None),
    image: UploadFile = File(None),
):
    """클레임 접수 (사진 업로드 포함)"""
    image_path = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1]
        filename = f"{uuid.uuid4().hex}{ext}"
        save_path = os.path.join(UPLOAD_DIR, filename)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_path = f"/uploads/{filename}"

    db = get_db()
    cursor = db.execute("""
        INSERT INTO claims (supplier, defect_type, ai_suggestion, cause_code, action, handler, image_path, memo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (supplier, defect_type, ai_suggestion, cause_code, action, handler, image_path, memo))
    db.commit()
    claim_id = cursor.lastrowid
    db.close()
    return {"message": "접수 완료", "claim_id": claim_id}


@router.put("/{claim_id}/status")
def update_status(claim_id: int, status: str = Form(...)):
    """클레임 상태 변경"""
    db = get_db()
    db.execute("UPDATE claims SET status = ? WHERE id = ?", (status, claim_id))
    db.commit()
    db.close()
    return {"message": "상태 업데이트 완료"}


@router.delete("/{claim_id}")
def delete_claim(claim_id: int):
    """클레임 삭제"""
    db = get_db()
    db.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
    db.commit()
    db.close()
    return {"message": "삭제 완료"}
