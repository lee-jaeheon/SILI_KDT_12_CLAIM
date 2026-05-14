import io
import logging
import os
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / "defect_detector.pt"
DEFAULT_CONF = float(os.getenv("YOLO_DET_CONF", "0.25"))

MODEL_NAME_TO_CODE = {
    "outer_damage": "OUTER_DAMAGE",
    "sealing": "SEALING",
    "hemming": "HEMMING",
    "hole_deform": "HOLE_DEFORM",
    "gap_defect": "GAP_DEFECT",
    "fastening_defect": "FASTENING_DEFECT",
}


def load_model():
    """Load the YOLOv8 detection model, or return None for dummy mode."""
    if not MODEL_PATH.exists():
        logger.warning("model file missing (%s); starting in dummy mode", MODEL_PATH)
        return None
    try:
        from ultralytics import YOLO

        model = YOLO(str(MODEL_PATH))
        logger.info("YOLOv8 detection model loaded: %s", MODEL_PATH)
        return model
    except Exception as exc:
        logger.error("model load failed: %s", exc)
        return None


def predict_detections(model, image_data: bytes, conf: float = DEFAULT_CONF) -> list[dict]:
    """
    Return detections as:
    [{"defect_code", "class_name", "confidence", "bbox_xywh", "bbox_xyxy"}, ...]
    """
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    result = model(img, verbose=False, conf=conf)[0]
    boxes = result.boxes
    if boxes is None:
        return []

    detections: list[dict] = []
    for box in boxes:
        cls_idx = int(box.cls[0])
        confidence = float(box.conf[0])
        class_name = result.names[cls_idx]
        defect_code = MODEL_NAME_TO_CODE.get(class_name, "OUTER_DAMAGE")
        xywh = [round(float(value), 2) for value in box.xywh[0].tolist()]
        xyxy = [round(float(value), 2) for value in box.xyxy[0].tolist()]
        detections.append(
            {
                "defect_code": defect_code,
                "class_name": class_name,
                "confidence": confidence,
                "bbox_xywh": xywh,
                "bbox_xyxy": xyxy,
            }
        )

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return detections


def predict_with_detections(
    model, image_data: bytes
) -> tuple[str | None, float, list[dict]]:
    detections = predict_detections(model, image_data)
    if not detections:
        return None, 0.0, []

    top = detections[0]
    return top["defect_code"], top["confidence"], detections


def predict(model, image_data: bytes) -> tuple[str | None, float]:
    """Backward-compatible wrapper for callers that only need one label."""
    defect_code, confidence, _detections = predict_with_detections(model, image_data)
    return defect_code, confidence
