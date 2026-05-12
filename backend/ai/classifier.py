import io
import logging
from pathlib import Path
from PIL import Image

from backend.core.defects import MODEL_NAME_TO_CODE

logger = logging.getLogger(__name__)

MODEL_DIR  = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "defect_classifier.pt"   # YOLOv8-cls 학습 모델


def load_model():
    """
    YOLOv8-cls 모델 로드.
    모델 파일 없으면 None 반환 → ai.py에서 더미 모드로 자동 전환.
    """
    if not MODEL_PATH.exists():
        logger.warning(f"모델 파일 없음({MODEL_PATH}) — 더미 모드로 동작")
        return None
    try:
        from ultralytics import YOLO
        model = YOLO(str(MODEL_PATH))
        logger.info(f"YOLOv8-cls 모델 로드 완료: {MODEL_PATH}")
        return model
    except Exception as e:
        logger.error(f"모델 로드 실패: {e}")
        return None


def predict(model, image_data: bytes) -> tuple[str, float]:
    """
    반환: (defect_code, confidence)
      defect_code : OUTER_DAMAGE / SEALING / HEMMING / HOLE_DEFORM 중 하나
      confidence  : 0.0 ~ 1.0
    """
    img     = Image.open(io.BytesIO(image_data)).convert("RGB")
    results = model(img, verbose=False)

    probs      = results[0].probs
    top1_idx   = int(probs.top1)
    confidence = float(probs.top1conf)
    class_name = results[0].names[top1_idx]          # ex) "hemming"

    defect_code = MODEL_NAME_TO_CODE.get(class_name, "OUTER_DAMAGE")
    return defect_code, confidence
