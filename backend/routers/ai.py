import io
import re
import json
import logging
import random

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pathlib import Path

from backend.ai.ollama import call_ollama
from backend.core.defects import DEFECT_CODES, label_of
from backend.core.uploads import read_with_limit, MAX_IMAGE_MB, MAX_DOC_MB
from backend.models.database import get_defect_types, search_similar
from backend.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ai"])

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
async def classify_image(image: UploadFile = File(...), _: dict = Depends(get_current_user)):
    image_data = await read_with_limit(image, MAX_IMAGE_MB)
    model = _get_model()

    if model:
        from backend.ai.classifier import predict
        defect_type, confidence = predict(model, image_data)
    else:
        defect_type = random.choice(DEFECT_CODES)
        confidence  = round(random.uniform(0.55, 0.92), 3)

    try:
        similar = search_similar(defect_type=defect_type, limit=3)
    except Exception as e:
        logger.warning(f"유사사례 검색 실패 (분류 결과는 정상): {e}")
        similar = []

    return {
        "defect_type":    defect_type,
        "label":          label_of(defect_type),
        "confidence":     confidence,
        "confidence_pct": f"{confidence * 100:.1f}%",
        "is_dummy":       model is None,
        "similar_cases":  similar,
    }


# ── AI 보고서 자동 생성 (YOLO + 클레임 텍스트 + 유사 사례 → LLM) ──────────────

@router.post("/generate-report")
async def generate_report(
    defect_type:    str  = Form(...),
    confidence:     float = Form(0.0),
    claim_text:     str  = Form(""),
    customer_name:  str  = Form(""),
    product_name:   str  = Form(""),
    defect_location: str = Form(""),
    _: dict = Depends(get_current_user),
):
    defect_label = label_of(defect_type)

    try:
        similar_cases = search_similar(
            defect_type=defect_type,
            customer_name=customer_name or None,
            product_name=product_name or None,
            defect_location=defect_location or None,
            claim_text=claim_text or None,
            limit=3,
            min_score=30,
        )
    except Exception as e:
        logger.warning(f"유사사례 검색 실패 (보고서 생성은 계속): {e}")
        similar_cases = []

    similar_text = ""
    for i, case in enumerate(similar_cases, 1):
        similar_text += f"""
[유사 사례 {i}] 고객사: {case.get('customer_name','')} / 불량유형: {label_of(case.get('defect_type',''))}
  - 원인 분석: {case.get('root_cause_analysis') or '없음'}
  - 시정 조치: {case.get('corrective_action') or '없음'}
  - 재발 방지: {case.get('preventive_action') or '없음'}
""".strip() + "\n"

    if not similar_text:
        similar_text = "유사 사례 없음"

    prompt = f"""당신은 자동차 부품 품질보증 전문가입니다.
아래 정보를 바탕으로 부적합 보고서의 세 항목을 작성하라.
반드시 JSON만 출력하고 설명은 쓰지 마라.

[불량 정보]
- 불량 유형: {defect_label} (AI 신뢰도: {confidence*100:.1f}%)
- 고객사: {customer_name or '미입력'}
- 제품명: {product_name or '미입력'}
- 불량 위치: {defect_location or '미입력'}
- 클레임 내용: {claim_text[:1000] if claim_text else '미입력'}

[유사 사례]
{similar_text}

출력 형식 (JSON):
{{"root_cause_analysis":"원인 분석 내용","corrective_action":"시정 조치 내용","preventive_action":"재발 방지 내용"}}

작성 기준:
- 유사 사례를 참고하되 현재 불량 정보에 맞게 구체적으로 작성할 것
- 각 항목은 2~4문장으로 작성할 것
- 한국어로 작성할 것
출력:"""

    try:
        response = await call_ollama(prompt)
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise HTTPException(status_code=500, detail="LLM 응답 파싱 실패")
        result = json.loads(match.group())
        result["similar_cases"] = similar_cases
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"보고서 생성 실패: {e}")


# ── 불량 유형 목록 ─────────────────────────────────────────────────────────────

@router.get("/defect-types")
def defect_types(_: dict = Depends(get_current_user)):
    return get_defect_types()


# ── 파일 텍스트 추출 ───────────────────────────────────────────────────────────

@router.post("/parse-file")
async def parse_file(file: UploadFile = File(...), _: dict = Depends(get_current_user)):
    data = await read_with_limit(file, MAX_DOC_MB)
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
async def parse_claim(text: str = Form(...), _: dict = Depends(get_current_user)):
    prompt = f"""아래 클레임 텍스트에서 정보를 추출해서 JSON으로 출력하라. 반드시 JSON만 출력하고 설명은 쓰지 마라.

출력 형식:
{{"customer_name":"고객사명","product_name":"품명","defect_type":"OUTER_DAMAGE또는SEALING또는HEMMING또는HOLE_DEFORM","delivery_quantity":수량숫자,"defect_quantity":불량수량숫자,"handler":"담당자이름","root_cause_analysis":"원인분석내용","corrective_action":"시정조치내용","preventive_action":"재발방지내용"}}

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
