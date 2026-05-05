import uuid
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.models.database import (
    insert_report, get_report, list_reports, update_report, delete_report,
    insert_image, get_images, delete_image,
    search_similar,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _save_image(image: UploadFile) -> str:
    ext = Path(image.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="지원하지 않는 이미지 형식입니다.")
    filename  = f"{uuid.uuid4().hex}{ext}"
    save_path = UPLOAD_DIR / filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(image.file, f)
    return f"/uploads/{filename}"


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/")
def get_reports(status: Optional[str] = Query(None)):
    return list_reports(status)


@router.post("/")
async def create_report(
    customer_name:     str            = Form(...),
    defect_type:       str            = Form(""),
    product_name:      str            = Form(""),
    product_no:        str            = Form(""),
    part_name:         str            = Form(""),
    process_name:      str            = Form(""),
    lot_no:            str            = Form(""),
    delivery_quantity: Optional[int]  = Form(None),
    defect_quantity:   Optional[int]  = Form(None),
    handler:           str            = Form(""),
    author_name:       str            = Form(""),
    delivery_date:     str            = Form(""),
    issue_date:        str            = Form(""),
    ai_defect_type:    str            = Form(""),
    ai_confidence:     Optional[float] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    image_path = None
    if image and image.filename:
        image_path = _save_image(image)

    report_id = insert_report(
        customer_name=customer_name,
        defect_type=defect_type or None,
        ai_defect_type=ai_defect_type or None,
        ai_confidence=ai_confidence,
        product_name=product_name or None,
        product_no=product_no or None,
        part_name=part_name or None,
        process_name=process_name or None,
        lot_no=lot_no or None,
        delivery_quantity=delivery_quantity,
        defect_quantity=defect_quantity,
        handler=handler or None,
        author_name=author_name or None,
        delivery_date=delivery_date or None,
        issue_date=issue_date or None,
    )

    if image_path:
        insert_image(report_id, image_path, image_type="불량부위")

    return {"report_id": report_id, "message": "보고서가 생성되었습니다.", "image_path": image_path}


@router.get("/similar")
def get_similar(
    defect_type:   str           = Query(...),
    customer_name: Optional[str] = Query(None),
    limit:         int           = Query(5),
):
    return search_similar(defect_type=defect_type, customer_name=customer_name, limit=limit)


@router.get("/{report_id}")
def get_report_detail(report_id: int):
    row = get_report(report_id)
    if not row:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    return row


class UpdateBody(BaseModel):
    defect_type:         Optional[str]   = None
    defect_code:         Optional[str]   = None
    product_name:        Optional[str]   = None
    product_no:          Optional[str]   = None
    part_name:           Optional[str]   = None
    process_name:        Optional[str]   = None
    lot_no:              Optional[str]   = None
    customer_name:       Optional[str]   = None
    delivery_quantity:   Optional[int]   = None
    defect_quantity:     Optional[int]   = None
    delivery_date:       Optional[str]   = None
    issue_date:          Optional[str]   = None
    root_cause_analysis: Optional[str]   = None
    corrective_action:   Optional[str]   = None
    preventive_action:   Optional[str]   = None
    handler:             Optional[str]   = None
    author_name:         Optional[str]   = None
    reviewer_name:       Optional[str]   = None
    approver_name:       Optional[str]   = None
    report_status:       Optional[str]   = None


@router.put("/{report_id}")
def update_report_api(report_id: int, body: UpdateBody):
    ok = update_report(report_id, body.model_dump(exclude_none=True))
    if not ok:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")
    return {"message": "수정되었습니다."}


@router.delete("/{report_id}")
def remove_report(report_id: int):
    delete_report(report_id)
    return {"message": "삭제되었습니다."}


# ── 이미지 관리 ────────────────────────────────────────────────────────────────

@router.post("/{report_id}/images")
async def add_image(
    report_id: int,
    image: UploadFile = File(...),
    image_type: str = Form(""),
    image_description: str = Form(""),
):
    image_path = _save_image(image)
    iid = insert_image(report_id, image_path, image_type or None, image_description or None)
    return {"image_id": iid, "image_path": image_path}


@router.get("/{report_id}/images")
def list_images(report_id: int):
    return get_images(report_id)


@router.delete("/images/{image_id}")
def remove_image(image_id: int):
    delete_image(image_id)
    return {"message": "삭제되었습니다."}
