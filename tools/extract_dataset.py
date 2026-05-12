# tar에서 클래스당 N장 무작위 추출 -> YOLOv8-cls dataset 구성
# 실행: .venv/Scripts/python tools/extract_dataset.py
# 소요 시간: 약 20~40분 (SSD 기준)
import sys, tarfile, random, time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from collections import defaultdict

# ── 설정 ──────────────────────────────────────────────────────
TRAIN_TARS = [
    Path("C:/ajin/Deeplearning/data/Training/원천데이터/TS_9.프레임_01.tar"),
    Path("C:/ajin/Deeplearning/data/Training/원천데이터/TS_9.프레임_02.tar"),
]
VAL_TAR     = Path("C:/ajin/Deeplearning/data/Validation/원천데이터/VS_9.프레임.tar")
OUT_DIR     = Path("dataset")
N_PER_CLASS = 3000
SEED        = 42

# 한국어 폴더명 → YOLOv8 영문 클래스명
CLASS_MAP = {
    "헤밍 불량": "hemming",
    "홀 변형":   "hole_deform",
    "외관 손상": "outer_damage",
    "실링 불량": "sealing",
}
CLASSES = list(CLASS_MAP.values())


def process_train_tar(tar_path: Path, need: dict, rng: random.Random) -> dict:
    """
    tar 1회 스캔 → 부족한 클래스의 이미지 추출
    getmembers()로 헤더만 읽고 → seek()로 필요 파일만 직접 추출 (효율적)
    """
    t0 = time.time()
    print(f"\n  [{tar_path.name}] 헤더 스캔 중...", flush=True)

    by_class = defaultdict(list)
    with tarfile.open(tar_path, "r") as tf:
        members = tf.getmembers()  # 헤더 + offset 정보만 읽음
        print(f"  스캔 완료 ({time.time()-t0:.0f}초) / 전체 {len(members)}개 항목")

        # 클래스별 분류 (부족한 클래스만)
        for m in members:
            if not m.isfile():
                continue
            parts = Path(m.name).parts
            if len(parts) >= 2 and parts[-2] in CLASS_MAP:
                eng = CLASS_MAP[parts[-2]]
                if need.get(eng, 0) > 0:
                    by_class[eng].append(m)

        for cls, lst in sorted(by_class.items()):
            print(f"    {cls}: 후보 {len(lst)}개 / 필요 {need.get(cls,0)}개")

        # 샘플링 후 추출
        print()
        for cls, pool in by_class.items():
            n      = min(need[cls], len(pool))
            chosen = rng.sample(pool, n)
            done   = 0
            for m in chosen:
                dest = OUT_DIR / "train" / cls / Path(m.name).name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    fobj = tf.extractfile(m)  # offset_data로 직접 seek
                    if fobj:
                        dest.write_bytes(fobj.read())
                done += 1
                if done % 500 == 0 or done == n:
                    print(f"    [{cls}] {done}/{n} 완료", flush=True)
            need[cls] -= n

    return need


def process_val_tar(tar_path: Path) -> int:
    """Validation tar 전체 추출 (3,265장 — 전부 사용)"""
    t0 = time.time()
    print(f"\n  [{tar_path.name}] 헤더 스캔 중...", flush=True)
    total = 0

    with tarfile.open(tar_path, "r") as tf:
        members = tf.getmembers()
        print(f"  스캔 완료 ({time.time()-t0:.0f}초) / 전체 {len(members)}개 항목")

        for m in members:
            if not m.isfile():
                continue
            parts = Path(m.name).parts
            if len(parts) < 2 or parts[-2] not in CLASS_MAP:
                continue
            eng  = CLASS_MAP[parts[-2]]
            dest = OUT_DIR / "val" / eng / Path(m.name).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                fobj = tf.extractfile(m)
                if fobj:
                    dest.write_bytes(fobj.read())
            total += 1
            if total % 500 == 0:
                print(f"  {total}개 완료...", flush=True)

    return total


def print_summary():
    print("\n" + "=" * 50)
    print("  데이터셋 구성 최종 결과")
    print("=" * 50)
    grand = 0
    for split in ["train", "val"]:
        sub = 0
        print(f"\n  {split}/")
        for cls in CLASSES:
            d = OUT_DIR / split / cls
            n = len(list(d.glob("*.*"))) if d.exists() else 0
            sub   += n
            grand += n
            bar    = "█" * (n // 100)
            print(f"    {cls:15s}: {n:5d}장  {bar}")
        print(f"    {'소계':15s}: {sub:5d}장")
    print(f"\n  총계: {grand}장")
    print("=" * 50)


if __name__ == "__main__":
    rng = random.Random(SEED)

    print("=" * 50)
    print("  YOLOv8-cls 데이터셋 추출")
    print(f"  Train: 클래스당 {N_PER_CLASS}장")
    print(f"  Val:   전체 사용 (~3,265장)")
    print("=" * 50)

    t_total = time.time()

    # ── Train 추출 ──────────────────────────────────────
    need = {cls: N_PER_CLASS for cls in CLASSES}

    print("\n[Train 1/2] TS_9.프레임_01 처리")
    need = process_train_tar(TRAIN_TARS[0], need, rng)

    # 부족한 클래스가 있으면 TS_02에서 보완
    short = {k: v for k, v in need.items() if v > 0}
    if short:
        print(f"\n  아직 부족: {short}")
        print("[Train 2/2] TS_9.프레임_02 처리 (부족분 보완)")
        need = process_train_tar(TRAIN_TARS[1], need, rng)
    else:
        print("\n  [Train 2/2] 모든 클래스 충족 — TS_02 스킵")

    # ── Val 추출 ────────────────────────────────────────
    print("\n[Val] VS_9.프레임 처리")
    val_total = process_val_tar(VAL_TAR)
    print(f"  Val 완료: {val_total}개")

    elapsed = time.time() - t_total
    print(f"\n  총 소요시간: {elapsed/60:.1f}분")
    print_summary()
