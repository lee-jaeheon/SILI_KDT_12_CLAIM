# AI Hub 자동차 부품 품질 데이터 (COCO JSON) → YOLOv8 Detection 포맷 변환
#
# 입력 구조 (AI Hub 원본):
#   data/01.데이터/
#     ├── 1.Training/
#     │   ├── 라벨링데이터/<부품>/<클래스>/*.json   (COCO 포맷)
#     │   └── 원천데이터/<부품>/<클래스>/*.jpg
#     └── 2.Validation/
#         ├── 라벨링데이터/<부품>/<클래스>/*.json
#         └── 원천데이터/<부품>/<클래스>/*.jpg
#
# 출력 구조 (YOLOv8 detection):
#   dataset_yolo/
#     ├── images/train/<file>.jpg
#     ├── images/val/<file>.jpg
#     ├── labels/train/<file>.txt     (한 줄당 한 박스, 정규화 좌표)
#     ├── labels/val/<file>.txt
#     └── data.yaml
#
# 실행: .venv/Scripts/python tools/extract_dataset_yolo.py
import sys, json, os, shutil, time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from collections import Counter

# ── 설정 ──────────────────────────────────────────────────────────────────────
SRC_ROOT = Path("c:/work/claim_system/data/01.데이터")
OUT_ROOT = Path("c:/work/claim_system/dataset_yolo")
PARTS    = ["프레임"]   # 부품 추가 시 여기에 ["프레임", "도어", ...] 식으로 늘리면 됨

# 이미지 배치 방식
#   "link" = 하드링크 (NTFS, 즉시, 디스크 0 추가 사용) - 추천
#   "copy" = 실복사 (디스크 +25GB, 10~20분)
IMG_MODE = "link"

# COCO category_id → YOLO class_id (현재 모델 클래스 순서 유지)
CATEGORY_TO_CLASS = {
    212: 0,   # 헤밍 불량 → hemming
    213: 1,   # 홀 변형 → hole_deform
    102: 2,   # 외관 손상 → outer_damage
    204: 3,   # 실링 불량 → sealing
    # 부품 추가 시 새 category_id 매핑을 여기에 추가
}

CLASS_NAMES = ["hemming", "hole_deform", "outer_damage", "sealing"]

SPLIT_MAP = {
    "1.Training":   "train",
    "2.Validation": "val",
}


def convert_one_json(json_path: Path, part: str):
    """
    JSON 1개를 읽어서:
      - YOLO 라벨 라인 리스트
      - 대응 이미지 파일 경로
    반환. 변환 실패 또는 대상 클래스 없으면 None.
    """
    try:
        # AI Hub 일부 JSON은 UTF-8 BOM 포함 → utf-8-sig로 읽음
        data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        return None, f"JSON 파싱 실패: {e}"

    images = data.get("images", [])
    if not images:
        return None, "images 항목 없음"

    img_info = images[0]
    W, H = img_info.get("width"), img_info.get("height")
    if not W or not H:
        return None, "이미지 크기 정보 없음"

    img_filename = img_info["file_name"]

    # bbox → YOLO 좌표 변환
    lines = []
    for ann in data.get("annotations", []):
        cat_id = ann.get("category_id")
        cls = CATEGORY_TO_CLASS.get(cat_id)
        if cls is None:
            continue   # 대상 4클래스 외는 스킵

        bbox = ann.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        x, y, w, h = bbox
        cx = (x + w / 2) / W
        cy = (y + h / 2) / H
        nw = w / W
        nh = h / H

        # 0~1 범위 안전성 체크 (이상치 제거)
        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < nw <= 1 and 0 < nh <= 1):
            continue

        lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

    if not lines:
        return None, "대상 클래스 annotation 없음"

    # 대응 이미지 경로
    # JSON: .../라벨링데이터/<부품>/<클래스>/<name>.json
    # IMG : .../원천데이터/<부품>/<클래스>/<name>.jpg
    json_class_dir = json_path.parent           # .../<클래스>
    class_name     = json_class_dir.name
    # split_root = .../1.Training 또는 2.Validation
    split_root     = json_class_dir.parent.parent.parent
    img_path = split_root / "원천데이터" / part / class_name / img_filename

    if not img_path.exists():
        return None, f"이미지 파일 없음: {img_path}"

    return (lines, img_path), None


def process_split(part: str, split_src: str, split_dst: str, counter: Counter, fail_reasons: Counter):
    label_dir = SRC_ROOT / split_src / "라벨링데이터" / part
    if not label_dir.exists():
        print(f"  [경로 없음] {label_dir}")
        return

    out_images = OUT_ROOT / "images" / split_dst
    out_labels = OUT_ROOT / "labels" / split_dst
    out_images.mkdir(parents=True, exist_ok=True)
    out_labels.mkdir(parents=True, exist_ok=True)

    json_files = list(label_dir.rglob("*.json"))
    print(f"  [{part}/{split_dst}] JSON {len(json_files)}개 발견")

    t0 = time.time()
    for i, json_path in enumerate(json_files, 1):
        result, err = convert_one_json(json_path, part)
        if result is None:
            fail_reasons[err] += 1
            continue

        lines, img_path = result

        # 같은 stem(파일명) 중복 방지: 부품_원본명 prefix 추가
        # 부품 여러 종 합쳐도 충돌 없게
        stem = f"{part}_{img_path.stem}"
        dst_img = out_images / f"{stem}{img_path.suffix}"
        dst_txt = out_labels / f"{stem}.txt"

        if not dst_img.exists():
            if IMG_MODE == "link":
                try:
                    os.link(img_path, dst_img)
                except OSError as e:
                    # 다른 드라이브 또는 NTFS 외 환경이면 복사로 폴백
                    fail_reasons[f"하드링크 실패 (복사 폴백): {e.strerror}"] += 1
                    shutil.copy2(img_path, dst_img)
            else:
                shutil.copy2(img_path, dst_img)
        dst_txt.write_text("\n".join(lines), encoding="utf-8")

        counter[(part, split_dst)] += 1

        if i % 500 == 0 or i == len(json_files):
            elapsed = time.time() - t0
            print(f"    {i}/{len(json_files)} 처리 ({elapsed:.0f}초, 변환 {counter[(part, split_dst)]}개)")


def write_data_yaml():
    yaml_path = OUT_ROOT / "data.yaml"
    yaml_path.write_text(
        f"""# YOLOv8 detection 학습용
path: {OUT_ROOT.resolve()}
train: images/train
val: images/val

nc: {len(CLASS_NAMES)}
names: {CLASS_NAMES}
""",
        encoding="utf-8",
    )
    print(f"\n  data.yaml 작성: {yaml_path}")


def main():
    print("=" * 60)
    print("  COCO JSON → YOLOv8 Detection 포맷 변환")
    print("=" * 60)
    print(f"  소스: {SRC_ROOT}")
    print(f"  출력: {OUT_ROOT}")
    print(f"  부품: {PARTS}")
    print(f"  클래스: {CLASS_NAMES}")
    print("=" * 60)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    counter      = Counter()
    fail_reasons = Counter()

    t_total = time.time()
    for part in PARTS:
        print(f"\n[{part}]")
        for split_src, split_dst in SPLIT_MAP.items():
            process_split(part, split_src, split_dst, counter, fail_reasons)

    write_data_yaml()

    # 요약
    print("\n" + "=" * 60)
    print("  변환 결과 요약")
    print("=" * 60)
    grand = 0
    for (part, split), n in sorted(counter.items()):
        print(f"  {part}/{split}: {n}장")
        grand += n
    print(f"  총계: {grand}장")

    if fail_reasons:
        print("\n  스킵된 항목:")
        for reason, n in fail_reasons.most_common():
            print(f"    [{n}] {reason}")

    elapsed = time.time() - t_total
    print(f"\n  소요시간: {elapsed/60:.1f}분")
    print("=" * 60)


if __name__ == "__main__":
    main()
