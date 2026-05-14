# YOLO Detection Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the AI Hub frame and connector tar archives into a filtered YOLO detection dataset and train a bbox-aware defect detector.

**Architecture:** A repository script streams label tar files, keeps only `attributes.quality == "불량품"` annotations, writes YOLO detection labels, then extracts only matching source images into `D:\Deeplearning\ajin\dataset_yolo_detection`. Training switches from YOLO classification to YOLO detection with `batch=8` for an 8GB GPU.

**Tech Stack:** Python stdlib `tarfile`, Ultralytics YOLOv8, existing FastAPI backend.

---

### Task 1: Dataset Conversion Script

**Files:**
- Create: `tools/extract_dataset_yolo_detection.py`
- Test: `tests/test_extract_dataset_yolo_detection.py`

- [x] Write unit tests for bbox conversion, class order, and output stem uniqueness.
- [x] Implement tar streaming label parsing with `quality == "불량품"` filtering.
- [x] Write `images/{train,val}`, `labels/{train,val}`, `data.yaml`, and `summary.json`.
- [x] Verify with `python -m unittest discover -s tests -p "test_*.py" -v` (the `tests.<module>` form clashes with a site-packages `tests` package inside `.venv`).

### Task 2: Detection Training

**Files:**
- Modify: `backend/ai/train.py`

- [x] Switch training from `yolov8n-cls.pt` to `yolov8n.pt`.
- [x] Use `D:\Deeplearning\ajin\dataset_yolo_detection\data.yaml`.
- [x] Set `imgsz=640`, `batch=8`, `cache=False`, `device=0`.
- [x] Save best weights to `models/defect_detector.pt`.

### Task 3: Detection Inference And Codes

**Files:**
- Modify: `backend/ai/classifier.py`
- Modify: `backend/routers/ai.py`
- Modify: `schema.sql`
- Modify: `backend/models/database.py`

- [x] Load `models/defect_detector.pt`.
- [x] Return the highest-confidence detection for legacy `/api/classify` compatibility.
- [x] Include all detections and bbox data in the API response.
- [x] Add `GAP_DEFECT` and `FASTENING_DEFECT` defect type seeds.

### Task 4: Verification

**Files:**
- Run checks only.

- [x] Run Python unit tests.
- [x] Run Python compile checks for modified backend scripts.
- [x] Run a small extraction smoke test before full dataset extraction.
- [x] Run full extraction to `D:\Deeplearning\ajin\dataset_yolo_detection` after the smoke test passes.
