# YOLOv8-cls 분류 모델 학습 스크립트
# 실행: .venv/Scripts/python backend/ai/train.py
import sys, time
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
from ultralytics import YOLO

DATASET_DIR = Path("dataset").resolve()
MODEL_SAVE  = Path("models/defect_detector.pt")
MODEL_SAVE.parent.mkdir(parents=True, exist_ok=True)

EPOCHS  = 50
IMGSZ   = 224
BATCH   = 32
WORKERS = 4

if __name__ == "__main__":
    print("=" * 55)
    print("  납품 불량 분류 모델 학습 시작")
    print("=" * 55)
    print(f"  데이터셋: {DATASET_DIR}")
    print(f"  Epochs : {EPOCHS}")
    print(f"  Imgsz  : {IMGSZ}px")
    print(f"  Batch  : {BATCH}")

    # 클래스별 이미지 수 출력
    for split in ["train", "val"]:
        print(f"\n  {split}/")
        for cls in sorted((DATASET_DIR / split).iterdir()):
            n = len(list(cls.glob("*.*")))
            print(f"    {cls.name:15s}: {n}장")

    print("\n" + "=" * 55)
    print("  학습 시작 (진행상황은 아래에 실시간 출력됩니다)")
    print("=" * 55 + "\n")

    t0 = time.time()

    model = YOLO("yolov8n-cls.pt")  # Pretrained 가중치 자동 다운로드

    results = model.train(
        data     = str(DATASET_DIR),
        epochs   = EPOCHS,
        imgsz    = IMGSZ,
        batch    = BATCH,
        workers  = WORKERS,
        project  = "models/runs",
        name     = "defect_cls",
        exist_ok = True,
        patience = 15,        # Early stopping
        cache    = False,
        device   = 0 if __import__('torch').cuda.is_available() else "cpu",
        verbose  = True,
    )

    # 최적 모델 복사
    best = Path("models/runs/defect_cls/weights/best.pt")
    if best.exists():
        import shutil
        shutil.copy(best, MODEL_SAVE)

    elapsed = time.time() - t0
    print("\n" + "=" * 55)
    print(f"  학습 완료  (소요시간: {elapsed/60:.1f}분)")
    print(f"  모델 저장: {MODEL_SAVE}")

    # 최종 정확도
    metrics = results.results_dict
    top1 = metrics.get("metrics/accuracy_top1", 0)
    top5 = metrics.get("metrics/accuracy_top5", 0)
    print(f"  Top-1 정확도: {top1:.1%}")
    print(f"  Top-5 정확도: {top5:.1%}")
    print("=" * 55)
