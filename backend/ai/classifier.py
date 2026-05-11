import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent.parent.parent / "defect_classifier.pt"

YOLO_TO_CODE = {
    "hemming":      "HEMMING",
    "hole_deform":  "HOLE_DEFORM",
    "outer_damage": "OUTER_DAMAGE",
    "sealing":      "SEALING",
}


def load_model():
    if not MODEL_PATH.exists():
        logger.warning("defect_classifier.pt 없음 — 더미 모드")
        return None
    try:
        from ultralytics import YOLO
        model = YOLO(str(MODEL_PATH))
        logger.info("YOLO 분류 모델 로드 완료: %s", MODEL_PATH.name)
        return model
    except Exception as e:
        logger.error("모델 로드 실패: %s", e)
        return None


def predict(model, image_data: bytes) -> tuple[str, float]:
    """반환: (defect_code, confidence)"""
    from PIL import Image
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    results = model(img, verbose=False)
    probs = results[0].probs
    class_name = results[0].names[probs.top1]
    confidence = float(probs.top1conf)
    defect_code = YOLO_TO_CODE.get(class_name, "OUTER_DAMAGE")
    return defect_code, confidence
