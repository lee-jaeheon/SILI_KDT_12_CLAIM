import io
import json
import logging
import torch
import timm
from pathlib import Path
from PIL import Image
from torchvision import transforms

logger = logging.getLogger(__name__)

MODEL_DIR      = Path(__file__).parent.parent.parent / "models"
MODEL_PATH     = MODEL_DIR / "best_model.pth"
CLASS_MAP_PATH = MODEL_DIR / "class_map.json"

FOLDER_TO_CODE = {
    "외관 손상": "OUTER_DAMAGE",
    "실링 불량": "SEALING",
    "헤밍 불량": "HEMMING",
    "홀 변형":   "HOLE_DEFORM",
}

TRANSFORM = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def load_model():
    if not MODEL_PATH.exists():
        logger.warning("best_model.pth 없음 — 더미 모드")
        return None
    try:
        class_map   = json.loads(CLASS_MAP_PATH.read_text(encoding="utf-8"))
        model = timm.create_model("tf_efficientnetv2_s", pretrained=False, num_classes=len(class_map))
        model.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
        model.eval()
        logger.info("EfficientNetV2-S 로드 완료")
        return (model, class_map)
    except Exception as e:
        logger.error(f"모델 로드 실패: {e}")
        return None


def predict(model_tuple, image_data: bytes) -> tuple[str, float]:
    """반환: (defect_code, confidence) — defect_code는 OUTER_DAMAGE 등 4개 코드 중 하나"""
    model, class_map = model_tuple
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    x   = TRANSFORM(img).unsqueeze(0)
    with torch.no_grad():
        probs = torch.softmax(model(x), dim=1)
        conf, idx = probs.max(dim=1)
    class_name  = class_map[str(idx.item())]
    defect_code = FOLDER_TO_CODE.get(class_name, "OUTER_DAMAGE")
    return defect_code, conf.item()
