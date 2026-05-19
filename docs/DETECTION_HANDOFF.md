# YOLOv8 Detection 학습 핸드오프

> **대상**: 딥러닝 담당자
> **목적**: AI Hub 자동차 부품 품질 데이터셋(COCO JSON)을 YOLOv8 Detection 학습 포맷으로 변환하고 학습하는 방법
> **준비된 도구**: `tools/extract_dataset_yolo.py` (변환 스크립트)
> **작성**: 2026-05-13

---

## 1. 왜 Detection으로 가나

현재 시스템은 YOLOv8-cls (Classification)으로 학습돼 있음.
- 입력: 이미지 1장
- 출력: 클래스 1개 + 신뢰도 ("이 사진은 HEMMING 87%")
- 위치 정보 없음

Detection으로 가면:
- 입력: 이미지 1장
- 출력: 박스 좌표 + 클래스 ("좌표 (120,340,80,60)에 HEMMING")
- **위치 + 다중 결함 동시 탐지 가능**

이걸 활용하면:
- 부위별 불량 히트맵 자동 누적 (사용자 클릭 없이)
- Pseudo-AR 가능 (사진 → 박스 표시)
- 한 사진 여러 결함 자동 분류
- AI Hub JSON의 bbox 정보 100% 활용

---

## 2. AI Hub 데이터 구조

```
data/01.데이터/
├── 1.Training/
│   ├── 라벨링데이터/        ← COCO JSON 파일들 (TL_*.tar)
│   │   └── 프레임/
│   │       ├── 헤밍 불량/  *.json
│   │       ├── 홀 변형/    *.json
│   │       ├── 외관 손상/  *.json
│   │       └── 실링 불량/  *.json
│   └── 원천데이터/          ← 이미지 (TS_*.tar)
│       └── 프레임/
│           ├── 헤밍 불량/  *.jpg
│           ├── ...
└── 2.Validation/
    ├── 라벨링데이터/
    └── 원천데이터/
```

각 JSON은 COCO 포맷:
- `images[0]` — 이미지 정보 (width, height, file_name)
- `annotations[]` — 각 결함의 bbox 좌표
  - `category_id`: 102(외관)/204(실링)/212(헤밍)/213(홀변형)
  - `bbox`: `[x좌상단, y좌상단, 너비, 높이]` 절대 픽셀

---

## 3. 변환 스크립트 — `tools/extract_dataset_yolo.py`

### 하는 일

COCO JSON → YOLOv8 Detection 포맷:
- 이미지: `dataset_yolo/images/{train,val}/<file>.jpg` (하드링크, 디스크 0 사용)
- 라벨: `dataset_yolo/labels/{train,val}/<file>.txt` (정규화 bbox)
- 설정: `dataset_yolo/data.yaml`

### 변환 규칙

COCO bbox `[x, y, w, h]` 픽셀 → YOLO `[cx, cy, w, h]` 정규화:
```
cx = (x + w/2) / 이미지_가로
cy = (y + h/2) / 이미지_세로
w_norm = w / 이미지_가로
h_norm = h / 이미지_세로
```

클래스 매핑 (CATEGORY_TO_CLASS):
- 212 헤밍 불량 → 0
- 213 홀 변형 → 1
- 102 외관 손상 → 2
- 204 실링 불량 → 3

### 출력 .txt 형식 (한 줄당 한 박스)

```
0 0.582122 0.372754 0.170058 0.505988
2 0.482101 0.534431 0.111138 0.170659
```

`class_id center_x center_y width height` (모두 0~1 정규화)

### 실행

```bash
# 1. 스크립트 안의 경로 설정 확인
#    SRC_ROOT = AI Hub 데이터 위치
#    OUT_ROOT = 출력 폴더
#    PARTS    = ["프레임"]  ← 다른 부품 추가 시 여기에

# 2. 실행 (변환 1~2분, 디스크 추가 사용 거의 0)
.venv/Scripts/python tools/extract_dataset_yolo.py
```

### 결과 (프레임만 학습 시)

| 항목 | 개수 |
|---|---|
| Training 이미지 + 라벨 | 7,216개 |
| Validation 이미지 + 라벨 | 1,807개 |
| 처리 시간 | ~12초 |
| 디스크 추가 사용 | ~326KB (라벨 txt만) |

---

## 4. 학습 — `backend/ai/train.py` 수정

### 현재 (Classification)

```python
model = YOLO("yolov8n-cls.pt")
results = model.train(
    data    = str(DATASET_DIR),   # 폴더 경로
    epochs  = 50,
    imgsz   = 224,
    batch   = 32,
    device  = 0,
)
```

### Detection으로 변경

```python
DATASET_YAML = Path("c:/work/claim_system/dataset_yolo/data.yaml")
MODEL_SAVE   = Path("models/defect_detector.pt")

model = YOLO("yolov8n.pt")        # cls 아닌 detection 모델
results = model.train(
    data    = str(DATASET_YAML),   # data.yaml 경로
    epochs  = 50,
    imgsz   = 640,                 # detection은 640 권장
    batch   = 16,                  # GPU 메모리 따라 조정
    device  = 0,
    project = "models/runs",
    name    = "defect_detect",
    patience = 15,
    cache   = False,
)
```

### 학습 시간 예상

RTX 4060 / 7000장 / 50 epochs / batch=16:
- 약 8~12시간 (밤새 실행 권장)

GPU 메모리 부족 시 `batch` 줄이기 (16 → 8 → 4).

---

## 5. 학습 후 — 시스템 통합

`backend/ai/classifier.py` 수정 (현재는 cls 추론):

### Detection 추론 함수 추가

```python
def predict_detection(model, image_data: bytes) -> list[dict]:
    """
    반환: [{"defect_code", "confidence", "bbox": [x,y,w,h]}, ...]
    한 사진에 여러 박스 가능
    """
    img = Image.open(io.BytesIO(image_data)).convert("RGB")
    results = model(img, verbose=False)
    
    boxes = results[0].boxes
    detections = []
    for box in boxes:
        cls_idx = int(box.cls[0])
        conf    = float(box.conf[0])
        x, y, w, h = box.xywh[0].tolist()
        
        cls_name = results[0].names[cls_idx]
        defect_code = MODEL_NAME_TO_CODE.get(cls_name, "OUTER_DAMAGE")
        
        detections.append({
            "defect_code": defect_code,
            "confidence":  conf,
            "bbox":        [x, y, w, h],
        })
    
    return detections
```

### 모델 파일 위치

- 현재 cls 모델: `models/defect_classifier.pt` (그대로 유지)
- 새 detection 모델: `models/defect_detector.pt` (별도)
- API는 둘 다 지원 가능 (cls는 안전망, detection은 위치 정보 제공)

---

## 6. 부품 추가 (도어, 후드 등)

새 부품을 학습 데이터에 넣으려면:

### 스크립트 수정 2곳만

```python
# tools/extract_dataset_yolo.py 상단

PARTS = ["프레임", "도어"]   # ← 추가

CATEGORY_TO_CLASS = {
    212: 0,  # 헤밍 불량
    213: 1,  # 홀 변형
    102: 2,  # 외관 손상
    204: 3,  # 실링 불량
    # 도어의 새 카테고리 ID 매핑 추가
    # 예: 203: 4,  # 단차 (도어용)
}

CLASS_NAMES = ["hemming", "hole_deform", "outer_damage", "sealing", "단차_door"]
```

데이터 위치: `data/01.데이터/{1.Training,2.Validation}/{원천데이터,라벨링데이터}/도어/`

### 실행

같은 명령어. 스크립트가 자동으로 부품별 처리:
```bash
.venv/Scripts/python tools/extract_dataset_yolo.py
```

학습:
```bash
.venv/Scripts/python backend/ai/train.py
```

---

## 7. 자주 묻는 질문

### Q. JSON 파일이 안 읽혀요 (BOM 에러)
A. 스크립트에 `utf-8-sig` 인코딩 처리 들어있음 (반영됨). 못 읽으면 JSON 파일 직접 확인.

### Q. 이미지 파일이 일부 없다고 나옵니다
A. AI Hub 원본 자체가 JSON > 이미지인 경우 있음. 스크립트가 자동 스킵하고 매칭되는 것만 처리. 정상.

### Q. 디스크 가득 차지 않나요?
A. 안 참. 이미지는 하드링크라 디스크 추가 사용 0. 라벨 txt만 ~326KB. 원본 그대로 두고 새 위치에서도 보이는 구조.

### Q. cls 모델은 어떻게 되나요?
A. 그대로 유지. detection 모델은 별도 파일(`defect_detector.pt`)로 저장하고, 시스템에서는 둘 중 하나 선택해서 쓸 수 있게 짜면 됨.

### Q. 학습 중간에 멈췄어요
A. `models/runs/defect_detect/weights/last.pt` 사용해서 이어 학습:
```python
model = YOLO("models/runs/defect_detect/weights/last.pt")
model.train(data="...", resume=True)
```

---

## 8. 체크리스트

학습 시작 전 확인:

- [ ] AI Hub 데이터 다운로드 완료 (원천데이터 + 라벨링데이터 둘 다)
- [ ] `tools/extract_dataset_yolo.py` 안의 `SRC_ROOT` 경로 확인
- [ ] 변환 스크립트 실행 → `dataset_yolo/` 생성 확인
- [ ] `data.yaml` 생성 확인
- [ ] `dataset_yolo/images/train/`, `dataset_yolo/labels/train/` 둘 다 같은 수 확인
- [ ] `backend/ai/train.py`에서 `yolov8n.pt` (detection) 사용 확인
- [ ] GPU 메모리 모니터링 (`nvidia-smi`)

---

## 9. 참고 자료

- YOLOv8 공식 문서: https://docs.ultralytics.com/
- YOLO Detection 포맷 설명: https://docs.ultralytics.com/datasets/detect/
- COCO 포맷 명세: https://cocodataset.org/#format-data
- AI Hub 자동차 부품 데이터: https://aihub.or.kr (검색: "자동차 부품 품질")

---

문의 사항 있으면 `tools/extract_dataset_yolo.py` 소스 보면서 백엔드 담당자에게 연락.
