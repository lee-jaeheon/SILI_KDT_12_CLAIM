"""Train the YOLOv8 detection model for defect bounding boxes."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

from ultralytics import YOLO

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_YAML = Path(os.getenv("AJIN_YOLO_DET_DATA", r"D:\Deeplearning\ajin\dataset_yolo_detection\data.yaml"))
MODEL_SAVE = BASE_DIR / "models" / "defect_detector.pt"
MODEL_SAVE.parent.mkdir(parents=True, exist_ok=True)

BASE_MODEL = os.getenv("YOLO_DET_BASE_MODEL", "yolov8n.pt")
EPOCHS = int(os.getenv("YOLO_DET_EPOCHS", "50"))
IMGSZ = int(os.getenv("YOLO_DET_IMGSZ", "640"))
BATCH = int(os.getenv("YOLO_DET_BATCH", "8"))  # Conservative default for 8GB VRAM.
WORKERS = int(os.getenv("YOLO_DET_WORKERS", "4"))
DEVICE = os.getenv("YOLO_DET_DEVICE", "0")


def _count_labels(dataset_yaml: Path) -> tuple[int, int]:
    root = dataset_yaml.parent
    train = len(list((root / "labels" / "train").glob("*.txt")))
    val = len(list((root / "labels" / "val").glob("*.txt")))
    return train, val


if __name__ == "__main__":
    if not DATASET_YAML.exists():
        raise FileNotFoundError(
            f"Dataset YAML not found: {DATASET_YAML}. "
            "Run tools/extract_dataset_yolo_detection.py first."
        )

    train_count, val_count = _count_labels(DATASET_YAML)

    print("=" * 60)
    print("  YOLOv8 defect detection training")
    print("=" * 60)
    print(f"  dataset : {DATASET_YAML}")
    print(f"  model   : {BASE_MODEL}")
    print(f"  epochs  : {EPOCHS}")
    print(f"  imgsz   : {IMGSZ}")
    print(f"  batch   : {BATCH} (8GB VRAM default)")
    print(f"  device  : {DEVICE}")
    print(f"  labels  : train={train_count:,}, val={val_count:,}")
    print("=" * 60 + "\n")

    started = time.time()
    model = YOLO(BASE_MODEL)
    results = model.train(
        data=str(DATASET_YAML),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        workers=WORKERS,
        project=str(BASE_DIR / "models" / "runs"),
        name="defect_detect",
        exist_ok=True,
        patience=15,
        cache=False,
        device=DEVICE,
        verbose=True,
    )

    best = BASE_DIR / "models" / "runs" / "defect_detect" / "weights" / "best.pt"
    if best.exists():
        shutil.copy2(best, MODEL_SAVE)

    metrics = getattr(results, "results_dict", {}) or {}
    print("\n" + "=" * 60)
    print(f"  training complete in {(time.time() - started) / 60:.1f} min")
    print(f"  saved model: {MODEL_SAVE}")
    if metrics:
        for key in ("metrics/mAP50(B)", "metrics/mAP50-95(B)", "metrics/precision(B)", "metrics/recall(B)"):
            if key in metrics:
                print(f"  {key}: {metrics[key]:.4f}")
    print("=" * 60)
