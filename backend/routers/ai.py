from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
import random  # TODO: 실제 모델로 교체 예정

router = APIRouter(prefix="/ai", tags=["ai"])

DEFECT_TYPES = ["외관손상", "실링 불량", "헤밍 불량", "홀 변형", "기타"]


@router.post("/classify")
async def classify_image(image: UploadFile = File(...)):
    """
    불량 이미지 → AI 불량 유형 제안
    현재: 임시 랜덤 반환 (추후 YOLO 모델로 교체)
    """
    # TODO: 실제 YOLO 모델 추론으로 교체
    # image_data = await image.read()
    # result = model.predict(image_data)

    # 임시 랜덤 응답 (시연용 placeholder)
    suggestion = random.choice(DEFECT_TYPES[:3])  # 외관 불량 위주
    confidence = round(random.uniform(0.70, 0.95), 2)

    return {
        "suggestion": suggestion,
        "confidence": confidence,
        "message": f"AI 분류 결과: {suggestion} (신뢰도 {int(confidence*100)}%)"
    }
