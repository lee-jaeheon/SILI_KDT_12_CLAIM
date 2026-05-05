import re
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.models.database import get_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["report"])

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "exaone3.5:7.8b"

DEFECT_LABELS = {
    "OUTER_DAMAGE": "외관 손상",
    "SEALING":      "실링 불량",
    "HEMMING":      "헤밍 불량",
    "HOLE_DEFORM":  "홀 변형",
}


async def _ollama(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            res = await client.post(OLLAMA_URL, json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            })
            res.raise_for_status()
            return res.json().get("response", "")
    except Exception as e:
        logger.error(f"Ollama 오류: {e}")
        raise


@router.get("/{report_id}/generate")
async def generate_report(report_id: int):
    report = get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="보고서를 찾을 수 없습니다.")

    defect_name = DEFECT_LABELS.get(report.get("defect_type", ""), "미확인")
    customer    = report.get("customer_name", "")
    received    = (report.get("received_date") or report.get("created_at", ""))[:10]
    root_cause  = report.get("root_cause_analysis") or "미기재"
    corrective  = report.get("corrective_action") or "미기재"
    preventive  = report.get("preventive_action") or "미기재"
    product     = report.get("product_name") or ""
    part        = report.get("part_name") or ""

    prompt = f"""당신은 제조업 품질관리 담당자입니다. 아래 정보를 바탕으로 품질 클레임 보고서 초안을 작성해줘.
각 섹션을 간결하고 전문적인 한국어로 작성해줘.

정보:
- 접수번호: {report.get('document_no', '')}
- 접수일자: {received}
- 납품처: {customer}
- 품명: {product} / 부품: {part}
- 불량유형: {defect_name}
- 담당자: {report.get('handler', '미배정')}
- 원인분석: {root_cause}
- 시정조치: {corrective}
- 재발방지: {preventive}

아래 JSON 형식으로만 출력해줘, 설명 없이:
{{"불량개요": "...", "원인분석": "...", "대책": "..."}}"""

    try:
        response = await _ollama(prompt)
        match    = re.search(r'\{.*\}', response, re.DOTALL)
        sections = json.loads(match.group()) if match else {}
    except Exception:
        sections = {
            "불량개요": f"납품처: {customer}\n품명: {product}\n불량유형: {defect_name}",
            "원인분석": root_cause,
            "대책":     corrective,
        }

    full_text = (
        f"【 품질 클레임 처리 보고서 】\n\n"
        f"■ 불량 개요\n{sections.get('불량개요', '')}\n\n"
        f"■ 원인 분석\n{sections.get('원인분석', '')}\n\n"
        f"■ 재발 방지 대책\n{sections.get('대책', '')}\n"
    )

    return {
        "report_id":   report_id,
        "document_no": report.get("document_no"),
        "customer":    customer,
        "received_at": received,
        "sections":    sections,
        "full_text":   full_text,
    }
