"""불량 유형 코드/라벨/시드의 단일 소스.

DB 의존 없는 순수 상수 모듈. ai/claim 응답, 분류기, DB seed 모두 여기서 가져간다.
새 불량 유형은 여기 한 곳만 추가하면 됨.
"""

# 부품 카테고리
PART_CATEGORIES = ["FRAME", "CONNECTOR"]
PART_CATEGORY_LABELS = {
    "FRAME":     "프레임",
    "CONNECTOR": "커넥터",
}

# 불량 코드 전체 목록
DEFECT_CODES = [
    "OUTER_DAMAGE",
    "SEALING",
    "HEMMING",
    "HOLE_DEFORM",
    "GAP_DEFECT",
    "FASTENING_DEFECT",
]

DEFECT_LABELS_KR = {
    "OUTER_DAMAGE":     "외관 손상",
    "SEALING":          "실링 불량",
    "HEMMING":          "헤밍 불량",
    "HOLE_DEFORM":      "홀 변형",
    "GAP_DEFECT":       "간격 불량",
    "FASTENING_DEFECT": "체결 불량",
}

# 부품 카테고리별 허용 불량 코드
DEFECT_CODES_BY_PART = {
    "FRAME":     ["OUTER_DAMAGE", "SEALING", "HEMMING", "HOLE_DEFORM"],
    "CONNECTOR": ["GAP_DEFECT", "FASTENING_DEFECT", "OUTER_DAMAGE"],
}

# YOLOv8 detection 모델 클래스명 → 시스템 코드
MODEL_NAME_TO_CODE = {
    "outer_damage":     "OUTER_DAMAGE",
    "sealing":          "SEALING",
    "hemming":          "HEMMING",
    "hole_deform":      "HOLE_DEFORM",
    "gap_defect":       "GAP_DEFECT",
    "fastening_defect": "FASTENING_DEFECT",
}

# defect_types 테이블 시드: (code, label, category_id, description)
DEFECT_SEED = [
    ("OUTER_DAMAGE",     DEFECT_LABELS_KR["OUTER_DAMAGE"],     102, "외관 긁힘, 찍힘, 변형 등 육안 식별 불량"),
    ("SEALING",          DEFECT_LABELS_KR["SEALING"],          204, "실링재 미도포, 부족, 위치 이탈"),
    ("HEMMING",          DEFECT_LABELS_KR["HEMMING"],          212, "헤밍 공정 접합 불량"),
    ("HOLE_DEFORM",      DEFECT_LABELS_KR["HOLE_DEFORM"],      213, "홀 치수 이탈, 변형"),
    ("GAP_DEFECT",       DEFECT_LABELS_KR["GAP_DEFECT"],       301, "커넥터 핀 간격 불량, 접점 이탈"),
    ("FASTENING_DEFECT", DEFECT_LABELS_KR["FASTENING_DEFECT"], 302, "커넥터 체결 불량, 락 미체결"),
]


def label_of(code: str) -> str:
    return DEFECT_LABELS_KR.get(code, code)


def part_label_of(category: str) -> str:
    return PART_CATEGORY_LABELS.get(category, category)


def defects_for_part(part_category: str) -> list[str]:
    return DEFECT_CODES_BY_PART.get(part_category, DEFECT_CODES)
