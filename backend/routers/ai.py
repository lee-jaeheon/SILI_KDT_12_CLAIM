import io
import re
import json
import logging
import random

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pathlib import Path

from backend.ai.ollama import call_ollama
from backend.models.database import get_defect_types

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ai"])

DEFECT_LABELS = {
    "OUTER_DAMAGE": "외관 손상",
    "SEALING":      "실링 불량",
    "HEMMING":      "헤밍 불량",
    "HOLE_DEFORM":  "홀 변형",
    "GAP_DEFECT":   "유격 불량",
    "FASTENING_DEFECT": "체결 불량",
}

# 서버 시작 시 모델 1회 로드
_model = None

def _get_model():
    global _model
    if _model is None:
        try:
            from backend.ai.classifier import load_model
            _model = load_model()
        except Exception as e:
            logger.error(f"모델 로드 실패: {e}")
            _model = False  # False = 로드 시도했으나 실패
    return _model if _model else None


# ── AI 이미지 분류 ─────────────────────────────────────────────────────────────

@router.post("/classify")
async def classify_image(image: UploadFile = File(...)):
    image_data = await image.read()
    model = _get_model()

    if model:
        from backend.ai.classifier import predict_with_detections
        defect_type, confidence, detections = predict_with_detections(model, image_data)
    else:
        defect_type = random.choice(list(DEFECT_LABELS.keys()))
        confidence  = round(random.uniform(0.55, 0.92), 3)
        detections = []

    if defect_type is None:
        label = "미검출"
        similar = []
    else:
        label = DEFECT_LABELS.get(defect_type, defect_type)
        from backend.models.database import search_similar
        similar = search_similar(defect_type=defect_type, limit=3)

    return {
        "defect_type":    defect_type,
        "label":          label,
        "confidence":     confidence,
        "confidence_pct": f"{confidence * 100:.1f}%",
        "detections":     detections,
        "bbox":           detections[0]["bbox_xywh"] if detections else None,
        "is_dummy":       model is None,
        "similar_cases":  similar,
    }


# ── 불량 유형 목록 ─────────────────────────────────────────────────────────────

@router.get("/defect-types")
def defect_types():
    return get_defect_types()


# ── 파일 텍스트 추출 ───────────────────────────────────────────────────────────

@router.post("/parse-file")
async def parse_file(file: UploadFile = File(...)):
    data = await file.read()
    ext  = Path(file.filename).suffix.lower()
    text = ""

    try:
        if ext == ".pdf":
            import pdfplumber, io as _io
            with pdfplumber.open(_io.BytesIO(data)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        elif ext == ".docx":
            from docx import Document
            import io as _io
            doc   = Document(_io.BytesIO(data))
            lines = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    lines.append(" | ".join(c.text.strip() for c in row.cells if c.text.strip()))
            text = "\n".join(lines)
        elif ext == ".eml":
            import email
            msg = email.message_from_bytes(data)
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    text += part.get_payload(decode=True).decode("utf-8", errors="ignore")
        else:
            raise HTTPException(status_code=400, detail="PDF, DOCX, EML 파일만 지원합니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 읽기 실패: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="파일에서 텍스트를 추출할 수 없습니다.")

    return {"extracted_text": text[:8000]}


# ── 텍스트 → 필드 파싱 (Ollama) ───────────────────────────────────────────────

@router.post("/parse-claim")
async def parse_claim(text: str = Form(...)):
    prompt = f"""아래 클레임 텍스트에서 정보를 추출해서 JSON으로 출력하라. 반드시 JSON만 출력하고 설명은 쓰지 마라.

출력 형식:
{{"customer_name":"고객사명","product_name":"품명","defect_type":"OUTER_DAMAGE또는SEALING또는HEMMING또는HOLE_DEFORM또는GAP_DEFECT또는FASTENING_DEFECT","delivery_quantity":수량숫자,"defect_quantity":불량수량숫자,"handler":"담당자이름","root_cause_analysis":"원인분석내용","corrective_action":"시정조치내용","preventive_action":"재발방지내용"}}

정보가 없으면 null로 채워라.

예시:
입력: "현대자동차 프레임 외관 손상 불량 30개 중 3개. 담당 이영수. 설비 충격으로 추정."
출력: {{"customer_name":"현대자동차","product_name":"프레임","defect_type":"OUTER_DAMAGE","delivery_quantity":30,"defect_quantity":3,"handler":"이영수","root_cause_analysis":"설비 충격으로 인한 외관 손상 추정","corrective_action":"설비 점검 및 충격 방지 조치","preventive_action":"정기 설비 점검 일정 수립"}}

클레임 텍스트:
{text}
출력:"""

    try:
        response = await call_ollama(prompt)
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="파싱 실패")
        return json.loads(match.group())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="JSON 파싱 실패")
