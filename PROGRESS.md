# 백엔드 진행 상황 (2026-05-06 기준)

## 완료된 작업

### DB 스키마 (MySQL)
- SQLite → MySQL 8.4 전환 완료
- 테이블 구조 확정 (팀원 스키마 기준으로 통일)

| 테이블 | 설명 |
|---|---|
| `defect_types` | 불량 유형 코드 테이블 |
| `defect_reports` | 클레임 보고서 메인 테이블 |
| `defect_report_images` | 보고서 첨부 이미지 |

> `claim_texts` 테이블 제거 — `defect_reports`에 `claim_text`, `extracted_text` 컬럼으로 통합

### 스키마 변경 내역
- `image_caption` 컬럼 제거 (사용 주체 불명확)
- `thumbnail_path` 컬럼 제거 (생성 로직 없음)
- `defect_bbox` 컬럼 유지 (YOLO 연동 가능성)

---

### API 엔드포인트

#### 보고서 CRUD
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/reports/` | 목록 조회 (페이지네이션) |
| POST | `/api/reports/` | 보고서 생성 |
| GET | `/api/reports/{id}` | 단건 조회 |
| PUT | `/api/reports/{id}` | 수정 |
| DELETE | `/api/reports/{id}` | 삭제 |
| GET | `/api/reports/similar` | 유사 사례 검색 |

#### 이미지
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/reports/{id}/images` | 이미지 추가 |
| GET | `/api/reports/{id}/images` | 이미지 목록 |
| DELETE | `/api/reports/images/{image_id}` | 이미지 삭제 |

#### AI
| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/classify` | 이미지 불량 분류 |
| POST | `/api/parse-file` | PDF/DOCX/EML 텍스트 추출 |
| POST | `/api/parse-claim` | 텍스트 → 필드 파싱 (Ollama) |
| GET | `/api/defect-types` | 불량 유형 코드 목록 |

---

### 개선 사항
- **페이지네이션**: `GET /api/reports/?page=1&limit=20` 형식으로 목록 조회
- **Ollama 에러 처리**: 연결 실패 503 / 타임아웃 504 / 서버 오류 502 구분 반환
- **입력 검증**: `defect_type` 값이 DB에 없는 코드면 400 에러 반환
- **공통 모듈**: `backend/ai/ollama.py` 로 LLM 호출 로직 통합

---

## AI팀 연동 필요 사항

| 항목 | 담당 | 상태 |
|---|---|---|
| `backend/ai/classifier.py` 모델 연결 | AI팀 | 미완 (현재 더미값 반환) |
| YOLO 연동 시 `defect_bbox` JSON 형식 전달 | AI팀 | 컬럼 준비됨 |

---

## 로컬 실행 방법

```bash
# 환경 변수 설정
cp .env.example .env
# .env에 DB 비밀번호 입력

# 서버 실행
python -m uvicorn backend.main:app --reload

# API 문서 확인
http://localhost:8000/docs
```

`.env` 파일은 Git에 올리지 않습니다. `.env.example` 참고해서 각자 생성하세요.
