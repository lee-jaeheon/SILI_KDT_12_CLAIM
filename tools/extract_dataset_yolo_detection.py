r"""Build a filtered YOLOv8 detection dataset from AI Hub tar archives.

The source tar files are read-only inputs. This script writes a new dataset to
``D:\Deeplearning\ajin\dataset_yolo_detection`` by default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

sys.stdout.reconfigure(encoding="utf-8")

SRC_ROOT = Path(r"D:\Deeplearning\ajin\data")
OUT_ROOT = Path(r"D:\Deeplearning\ajin\dataset_yolo_detection")

CATEGORY_TO_CLASS = {
    212: 0,  # hemming
    213: 1,  # hole_deform
    102: 2,  # outer_damage
    204: 3,  # sealing
    207: 4,  # gap_defect
    209: 5,  # fastening_defect
}

CLASS_NAMES = [
    "hemming",
    "hole_deform",
    "outer_damage",
    "sealing",
    "gap_defect",
    "fastening_defect",
]

SPLITS = {
    "Training": ("train", "TL_", "TS_"),
    "Validation": ("val", "VL_", "VS_"),
}

PART_KEYS = ["frame", "connecter"]


@dataclass(frozen=True)
class LabelRecord:
    part_key: str
    split: str
    class_ids: tuple[int, ...]
    image_member: str
    image_out: Path
    label_out: Path
    lines: tuple[str, ...]


def normalize_yolo_bbox(
    bbox: list[float] | tuple[float, ...],
    *,
    image_width: int | float,
    image_height: int | float,
) -> tuple[float, float, float, float] | None:
    if len(bbox) != 4 or image_width <= 0 or image_height <= 0:
        return None

    x, y, w, h = [float(v) for v in bbox]
    if w <= 0 or h <= 0:
        return None
    if x < 0 or y < 0 or x + w > image_width or y + h > image_height:
        return None

    cx = (x + w / 2) / image_width
    cy = (y + h / 2) / image_height
    nw = w / image_width
    nh = h / image_height

    values = (round(cx, 6), round(cy, 6), round(nw, 6), round(nh, 6))
    if not (0 <= values[0] <= 1 and 0 <= values[1] <= 1 and 0 < values[2] <= 1 and 0 < values[3] <= 1):
        return None
    return values


def make_output_stem(part_key: str, image_member: str) -> str:
    stem = Path(PurePosixPath(image_member).name).stem
    digest = hashlib.sha1(image_member.encode("utf-8")).hexdigest()[:10]
    safe_stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return f"{part_key}_{safe_stem}_{digest}"


def _find_tars(split_root: Path, prefix: str) -> list[Path]:
    return sorted(path for path in split_root.rglob("*.tar") if path.name.startswith(prefix))


def _iter_label_records(
    *,
    label_tar: Path,
    out_root: Path,
    part_key: str,
    split: str,
    limit_per_class: int | None,
    class_seen: Counter,
    stats: Counter,
) -> Iterable[LabelRecord]:
    with tarfile.open(label_tar, "r") as tf:
        for member in tf:
            if not (member.isfile() and member.name.endswith(".json")):
                continue

            stats["json_files"] += 1
            try:
                raw = tf.extractfile(member)
                if raw is None:
                    stats["json_read_failed"] += 1
                    continue
                data = json.loads(raw.read().decode("utf-8-sig"))
            except Exception:
                stats["json_parse_failed"] += 1
                continue

            image_info = (data.get("images") or [{}])[0]
            image_width = image_info.get("width")
            image_height = image_info.get("height")
            image_filename = image_info.get("file_name")
            if not image_width or not image_height or not image_filename:
                stats["missing_image_info"] += 1
                continue

            lines: list[str] = []
            class_ids: list[int] = []
            for ann in data.get("annotations", []):
                attrs = ann.get("attributes") or {}
                if attrs.get("quality") != "불량품":
                    stats["skipped_quality"] += 1
                    continue

                cls = CATEGORY_TO_CLASS.get(ann.get("category_id"))
                if cls is None:
                    stats["skipped_unknown_category"] += 1
                    continue

                if limit_per_class is not None and class_seen[(split, cls)] >= limit_per_class:
                    stats["skipped_limit"] += 1
                    continue

                normalized = normalize_yolo_bbox(
                    ann.get("bbox") or [],
                    image_width=image_width,
                    image_height=image_height,
                )
                if normalized is None:
                    stats["skipped_invalid_bbox"] += 1
                    continue

                cx, cy, nw, nh = normalized
                lines.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
                class_ids.append(cls)

            if not lines:
                stats["skipped_no_valid_annotation"] += 1
                continue

            for cls in set(class_ids):
                class_seen[(split, cls)] += 1

            label_parent = PurePosixPath(member.name).parent
            image_member = str(label_parent / image_filename)
            out_stem = make_output_stem(part_key, image_member)
            suffix = Path(image_filename).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                stats["skipped_unsupported_image_ext"] += 1
                continue

            yield LabelRecord(
                part_key=part_key,
                split=split,
                class_ids=tuple(class_ids),
                image_member=image_member,
                image_out=out_root / "images" / split / f"{out_stem}{suffix}",
                label_out=out_root / "labels" / split / f"{out_stem}.txt",
                lines=tuple(lines),
            )


def collect_records(src_root: Path, out_root: Path, limit_per_class: int | None) -> tuple[list[LabelRecord], Counter]:
    records: list[LabelRecord] = []
    stats: Counter = Counter()
    class_seen: Counter = Counter()

    for part_key in PART_KEYS:
        part_root = src_root / part_key
        if not part_root.exists():
            stats[f"missing_part_{part_key}"] += 1
            continue

        for split_dir, (split, label_prefix, _image_prefix) in SPLITS.items():
            label_tars = _find_tars(part_root / split_dir, label_prefix)
            if not label_tars:
                stats[f"missing_label_tar_{part_key}_{split}"] += 1
                continue

            for label_tar in label_tars:
                print(f"  label scan: {label_tar}")
                part_records = list(
                    _iter_label_records(
                        label_tar=label_tar,
                        out_root=out_root,
                        part_key=part_key,
                        split=split,
                        limit_per_class=limit_per_class,
                        class_seen=class_seen,
                        stats=stats,
                    )
                )
                records.extend(part_records)
                print(f"    kept records: {len(part_records):,}")

    return records, stats


def extract_images(src_root: Path, records: list[LabelRecord], overwrite: bool) -> tuple[set[str], Counter]:
    stats: Counter = Counter()
    needed_by_split_part: dict[tuple[str, str], dict[str, Path]] = defaultdict(dict)
    for record in records:
        needed_by_split_part[(record.part_key, record.split)][record.image_member] = record.image_out

    extracted: set[str] = set()
    for part_key in PART_KEYS:
        part_root = src_root / part_key
        for split_dir, (split, _label_prefix, image_prefix) in SPLITS.items():
            needed = needed_by_split_part.get((part_key, split), {})
            if not needed:
                continue

            image_tars = _find_tars(part_root / split_dir, image_prefix)
            if not image_tars:
                stats[f"missing_image_tar_{part_key}_{split}"] += len(needed)
                continue

            remaining = set(needed.keys())
            for image_tar in image_tars:
                if not remaining:
                    break
                print(f"  image extract: {image_tar}")
                with tarfile.open(image_tar, "r") as tf:
                    for member in tf:
                        if not (member.isfile() and member.name in remaining):
                            continue

                        dst = needed[member.name]
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if overwrite or not dst.exists():
                            src = tf.extractfile(member)
                            if src is None:
                                stats["image_read_failed"] += 1
                                continue
                            tmp = dst.with_suffix(dst.suffix + ".tmp")
                            with tmp.open("wb") as out:
                                shutil.copyfileobj(src, out)
                            tmp.replace(dst)

                        remaining.remove(member.name)
                        extracted.add(member.name)
                        stats["images_extracted"] += 1

                print(f"    remaining for {part_key}/{split}: {len(remaining):,}")

            for missing in remaining:
                stats[f"missing_image_{part_key}_{split}"] += 1
                stats[f"missing::{missing}"] += 1

    return extracted, stats


def write_labels_and_yaml(out_root: Path, records: list[LabelRecord], extracted: set[str], overwrite: bool) -> Counter:
    stats: Counter = Counter()
    per_class: Counter = Counter()

    for record in records:
        if record.image_member not in extracted and not record.image_out.exists():
            stats["labels_skipped_missing_image"] += 1
            continue

        record.label_out.parent.mkdir(parents=True, exist_ok=True)
        if overwrite or not record.label_out.exists():
            record.label_out.write_text("\n".join(record.lines) + "\n", encoding="utf-8")
        stats[f"labels_{record.split}"] += 1
        for cls in record.class_ids:
            per_class[(record.split, CLASS_NAMES[cls])] += 1

    yaml_path = out_root / "data.yaml"
    yaml_path.write_text(
        "\n".join(
            [
                f"path: {out_root.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "",
                f"nc: {len(CLASS_NAMES)}",
                f"names: {CLASS_NAMES}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = {
        "output_root": str(out_root.resolve()),
        "classes": CLASS_NAMES,
        "label_files": {key: value for key, value in stats.items()},
        "annotations_per_class": {f"{split}/{name}": count for (split, name), count in sorted(per_class.items())},
    }
    (out_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats + per_class


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-root", type=Path, default=SRC_ROOT)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--limit-per-class", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-images", action="store_true", help="Only scan labels and write data.yaml summary.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.time()

    print("=" * 70)
    print("  AI Hub tar -> YOLOv8 detection dataset")
    print("=" * 70)
    print(f"  source : {args.src_root}")
    print(f"  output : {args.out_root}")
    print(f"  classes: {CLASS_NAMES}")
    print(f"  limit  : {args.limit_per_class or 'none'}")
    print("=" * 70)

    args.out_root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        (args.out_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.out_root / "labels" / split).mkdir(parents=True, exist_ok=True)

    records, scan_stats = collect_records(args.src_root, args.out_root, args.limit_per_class)
    if args.skip_images:
        extracted = {record.image_member for record in records if record.image_out.exists()}
        image_stats = Counter()
    else:
        extracted, image_stats = extract_images(args.src_root, records, args.overwrite)
    write_stats = write_labels_and_yaml(args.out_root, records, extracted, args.overwrite)

    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    for key, value in sorted((scan_stats + image_stats + write_stats).items(), key=lambda item: str(item[0])):
        if str(key).startswith("missing::"):
            continue
        print(f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}")
    print(f"  elapsed_min: {(time.time() - started) / 60:.1f}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
