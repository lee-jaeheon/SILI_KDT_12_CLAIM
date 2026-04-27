# 납품 불량 클레임 대응 자동화 시스템

**2026 제3회 SILI 경진대회** | 경북대 KDT 12기 | 팀원: 문종필, 박용비, 이재헌, 정준하

---

## 개요
MES·QMS 미도입 중소 협력사(2차 벤더 이하)의 납품 불량 클레임 대응 업무를 자동화하는 시스템

- 클레임 통합 접수 (불량 사진 업로드)
- AI 보조 불량 유형 분류 (Human-in-the-loop)
- 유사 사례 검색 → 보고서 초안 자동 생성
- 품질 노하우 DB 영구 축적

---

## 기술 스택
- **Backend**: Python, FastAPI
- **Frontend**: HTML, CSS, JS
- **DB**: SQLite
- **AI**: CNN (YOLO), OpenCV

---

## 시작하기

### 1. 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. DB 초기화 (최초 1회)
```bash
python init_db.py
```

### 3. 서버 실행
```bash
python run.py
```
브라우저가 자동으로 열립니다 → http://localhost:8000

---

## 폴더 구조
```
SILI_KDT_12_CLAIM/
├── backend/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── routers/
│   │   ├── claim.py         # 클레임 접수/조회 API
│   │   ├── report.py        # 보고서 초안 생성 API
│   │   └── ai.py            # AI 분류 API
│   ├── models/
│   │   └── database.py      # SQLite 연결
│   └── ai/
│       └── classifier.py    # CNN 모델 (추후 구현)
├── frontend/
│   ├── index.html           # 클레임 접수 페이지
│   ├── list.html            # 클레임 목록 페이지
│   ├── search.html          # 유사 사례 검색 페이지
│   ├── css/style.css
│   └── js/main.js
├── database/                # SQLite DB (gitignore)
├── init_db.py               # DB 초기화
├── run.py                   # 실행 진입점
└── requirements.txt
```

---

## 확장 로드맵
- **시나리오 1** (현재): 로컬 .exe 단일 PC 실행
- **시나리오 2** (1차 확장): 사내망 서버 연동, 다중 사용자
- **시나리오 3** (장기): 고객사 모바일 앱 연동
