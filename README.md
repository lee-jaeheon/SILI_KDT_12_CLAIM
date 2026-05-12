# 납품 불량 클레임 대응 자동화 시스템

**2026 제3회 SILI 경진대회** | 경북대 KDT 12기 | 팀원: 문종필, 박용비, 이재헌, 정준하

---

## 개요

MES·QMS 미도입 중소 협력사(2차 벤더 이하)의 납품 불량 클레임 대응 업무를 자동화하는 시스템.

- PDF/DOCX/EML 클레임 문서 업로드 → 텍스트 자동 파싱 및 필드 추출 (Ollama LLM)
- 불량 사진 업로드 → YOLOv8-cls 불량 유형 분류
- 유사 사례 검색 (가중치 기반 SequenceMatcher) → 보고서 초안 자동 작성
- 부적합 처리 보고서(NCR) Word 문서 자동 생성 및 다운로드
- 처리 완료 보고서의 유사 사례 DB 영구 축적

---

## 기술 스택

| 구분 | 내용 |
|---|---|
| Backend | Python 3.10+, FastAPI, PyMySQL |
| Frontend | HTML / CSS / Vanilla JS |
| DB | MySQL 8.x |
| 이미지 분류 | YOLOv8-cls (ultralytics) |
| 텍스트 파싱 | Ollama LLM (로컬, exaone3.5 권장) |
| 문서 생성 | python-docx |

---

## 로컬 실행

### 1. 사전 준비

- Python 3.10 이상 (이미지 분류 사용 시 ultralytics 호환 환경 필요)
- MySQL 8.x 실행 중
- Ollama 설치 및 모델 로드 (LLM 파싱 사용 시)
- 학습된 모델 파일을 `models/defect_classifier.pt`에 배치 (없으면 더미 응답 반환, `is_dummy: true`)

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env.example`을 복사해 `.env` 생성 후 DB 접속 정보 입력:

```bash
cp .env.example .env
# .env 파일에 DB_HOST, DB_USER, DB_PASSWORD 등 수정
```

### 4. DB 초기화 (최초 1회)

`schema.sql`을 MySQL에 실행하거나:

```bash
python init_db.py
```

### 5. 서버 실행

```bash
python run.py
```

브라우저에서 → http://localhost:8000

---

## 폴더 구조

```
merged_repo/
├── backend/
│   ├── main.py                          # FastAPI 앱 진입점·페이지 라우트·정적 파일
│   ├── routers/
│   │   ├── claim.py                     # 보고서 CRUD, Word 생성·다운로드, 이미지 API
│   │   └── ai.py                        # 이미지 분류, 파일 파싱, LLM 호출 API
│   ├── models/
│   │   └── database.py                  # MySQL 연결, CRUD, 유사사례 검색
│   ├── ai/
│   │   ├── classifier.py                # YOLOv8-cls 추론
│   │   ├── train.py                     # 학습 스크립트
│   │   └── ollama.py                    # Ollama LLM 호출 공통 모듈
│   └── 부적합_처리_보고서_양식.docx      # NCR Word 양식 템플릿
├── frontend/
│   ├── index.html                       # 로그인
│   ├── hub.html                         # 메인 허브 (3개 카드: 신규접수/목록/유사사례)
│   ├── claim_step1.html                 # 1단계: 클레임 접수 (파일/이미지 업로드)
│   ├── claim_step2.html                 # 2단계: 추출 결과 확인·수정
│   ├── report-download.html             # 3단계: 미리보기·Word 다운로드
│   ├── list.html                        # 보고서 목록
│   ├── cases.html                       # 유사 사례 검색
│   ├── css/style.css
│   ├── js/main.js
│   └── fonts/
├── tools/
│   └── extract_dataset.py               # YOLOv8 학습용 데이터셋 추출
├── models/                              # 학습 모델 가중치 (gitignore)
├── uploads/                             # 업로드 이미지 (gitignore)
├── schema.sql                           # MySQL 스키마
├── init_db.py                           # DB 초기화 스크립트
├── run.py                               # 서버 실행 진입점
├── requirements.txt
└── .env.example
```

---

## 페이지 흐름

```
/  (login)
 └─ /hub
     ├─ /claim       → /claim-step2 → /claim-step3 (보고서 다운로드)
     ├─ /list        보고서 전체 목록·상태 변경·삭제
     └─ /cases       유사 사례 검색
```

---

## API 엔드포인트 요약

### 보고서

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/reports/` | 목록 조회 (페이지네이션) |
| POST | `/api/reports/` | 보고서 생성 |
| GET | `/api/reports/{id}` | 단건 조회 |
| PUT | `/api/reports/{id}` | 수정 |
| PATCH | `/api/reports/{id}/status` | 상태 변경 |
| DELETE | `/api/reports/{id}` | 삭제 |
| GET | `/api/reports/{id}/preview` | Word 문서 미리보기 (inline) |
| GET | `/api/reports/{id}/download` | Word 문서 다운로드 |
| GET | `/api/reports/similar` | 유사 사례 검색 |

### 이미지

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/reports/{id}/images` | 이미지 추가 |
| GET | `/api/reports/{id}/images` | 이미지 목록 |
| DELETE | `/api/reports/images/{image_id}` | 이미지 삭제 |

### AI

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/api/classify` | 불량 이미지 분류 (YOLOv8-cls) |
| POST | `/api/parse-file` | PDF/DOCX/EML 텍스트 추출 |
| POST | `/api/parse-claim` | 텍스트 → 보고서 필드 파싱 (Ollama) |
| GET | `/api/defect-types` | 불량 유형 코드 목록 |

---

## 이미지 분류 모델

학습된 YOLOv8-cls 가중치 파일을 `models/defect_classifier.pt`에 배치하면 자동 로드됩니다.
모델 파일이 없으면 시연용 랜덤값을 반환하며, 응답의 `is_dummy: true` 플래그로 구분 가능합니다.

지원 클래스 (4종): `OUTER_DAMAGE`, `SEALING`, `HEMMING`, `HOLE_DEFORM`

학습은 `backend/ai/train.py`로 수행. 데이터셋 준비는 `tools/extract_dataset.py` 참조.

---

## 보고서 상태 흐름

```
draft → submitted → approved
                  ↘ rejected
```

`approved` 상태 보고서만 유사 사례 검색에 활용됩니다.
