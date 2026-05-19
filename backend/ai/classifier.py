import io
import logging
from pathlib import Path
from PIL import Image

from backend.core.defects import MODEL_NAME_TO_CODE

logger = logging.getLogger(__name__)

MODEL_DIR  = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "defect_detector.pt"   # YOLOv8 detection 모델


def load_model():
    """
    YOLOv8 detection 모델 로드.
    모델 파일 없으면 None 반환 → ai.py에서 더미 모드로 자동 전환.
    """
    if not MODEL_PATH.exists():
        logger.warning(f"모델 파일 없음({MODEL_PATH}) — 더미 모드로 동작")
        return None
    try:
        from ultralytics import YOLO
        model = YOLO(str(MODEL_PATH))
        logger.info(f"YOLOv8 detection 모델 로드 완료: {MODEL_PATH}")
        return model
    except Exception as e:
        logger.error(f"모델 로드 실패: {e}")
        return None


def predict(model, image_data: bytes) -> tuple[str | None, float]:
    """
    YOLOv8 detection 기반 불량 분류.

    반환: (defect_code, confidence)
      defect_code : OUTER_DAMAGE / SEALING / HEMMING / HOLE_DEFORM /
                    GAP_DEFECT / FASTENING_DEFECT
                    미검출 시 None
      confidence  : 0.0 ~ 1.0
    """
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    results = model(img, verbose=False)

    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        logger.info("미검출: 감지된 불량 없음")
        return None, 0.0

    # 신뢰도 가장 높은 박스 선택
    best_idx   = int(boxes.conf.argmax())
    class_idx  = int(boxes.cls[best_idx])
    confidence = float(boxes.conf[best_idx])
    class_name = results[0].names[class_idx]

    defect_code = MODEL_NAME_TO_CODE.get(class_name)
    if defect_code is None:
        logger.warning(f"알 수 없는 클래스명: {class_name}")
        return None, 0.0

    return defect_code, confidence
