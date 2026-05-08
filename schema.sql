-- ============================================================
--  납품 불량 클레임 대응 자동화 시스템
--  DB 스키마 (MySQL 8.x / InnoDB / utf8mb4)
--
--  테이블 목록
--    1. defect_types          불량 유형 코드 (lookup)
--    2. document_sequences    문서번호 채번 관리
--    3. defect_reports        불량 보고서 (핵심)
--    4. defect_report_images  보고서 첨부 이미지
-- ============================================================

CREATE DATABASE IF NOT EXISTS claims_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE claims_db;


-- ------------------------------------------------------------
--  1. defect_types
--     불량 유형 코드 테이블 (lookup)
--     defect_reports.defect_type 의 FK 대상
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS defect_types (
    code        VARCHAR(50)  PRIMARY KEY          COMMENT '불량 유형 코드 (예: OUTER_DAMAGE)',
    label       VARCHAR(100) NOT NULL             COMMENT '표시 이름 (예: 외관 손상)',
    category_id INT                               COMMENT '카테고리 분류 번호',
    description TEXT                              COMMENT '상세 설명'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='불량 유형 코드 테이블';

-- 기본 데이터
INSERT IGNORE INTO defect_types (code, label, category_id, description) VALUES
    ('OUTER_DAMAGE', '외관 손상', 102, '외관 긁힘, 찍힘, 변형 등 육안 식별 불량'),
    ('SEALING',      '실링 불량', 204, '실링재 미도포, 부족, 위치 이탈'),
    ('HEMMING',      '헤밍 불량', 212, '헤밍 공정 접합 불량'),
    ('HOLE_DEFORM',  '홀 변형',   213, '홀 치수 이탈, 변형');


-- ------------------------------------------------------------
--  2. document_sequences
--     문서번호 자동 채번용 (연도별 시퀀스)
--     문서번호 형식: AJ-QA-{YYYY}-{NNNN}
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_sequences (
    seq_year INT PRIMARY KEY              COMMENT '연도 (예: 2026)',
    last_seq INT NOT NULL DEFAULT 0      COMMENT '해당 연도 마지막 채번 번호'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='문서번호 채번 관리';


-- ------------------------------------------------------------
--  3. defect_reports
--     불량 보고서 핵심 테이블
--
--  상태(report_status) 전이:
--    draft → submitted → approved
--                      ↘ rejected
--
--  approved 상태 레코드는 유사 사례 검색(search_similar)에 활용
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS defect_reports (

    -- 식별자
    report_id       INT         PRIMARY KEY AUTO_INCREMENT  COMMENT '보고서 고유 ID',
    document_no     VARCHAR(20) UNIQUE                      COMMENT '문서 번호 (AJ-QA-YYYY-NNNN)',

    -- 날짜
    received_date   DATE                                    COMMENT '접수일 (생성 시 자동 입력)',
    issue_date      DATE                                    COMMENT '문서 발행일',
    delivery_date   DATE                                    COMMENT '납품일',

    -- 불량 정보
    defect_type     VARCHAR(50)                             COMMENT '불량 유형 코드 (FK → defect_types)',
    defect_code     VARCHAR(50)                             COMMENT '불량 코드 (예: M01)',
    defect_location VARCHAR(200)                            COMMENT '불량 발생 위치',

    -- 고객 / 제품
    customer_name   VARCHAR(200) NOT NULL                   COMMENT '고객사명',
    product_name    VARCHAR(200)                            COMMENT '품명 (제품 이름)',
    product_no      VARCHAR(100)                            COMMENT '품번 (제품 번호)',
    part_name       VARCHAR(200)                            COMMENT '부품명',
    process_name    VARCHAR(200)                            COMMENT '공정명',
    lot_no          VARCHAR(100)                            COMMENT 'LOT No.',
    delivery_quantity INT                                   COMMENT '납품 수량',
    defect_quantity   INT                                   COMMENT '불량 수량',

    -- 클레임 텍스트
    claim_text      LONGTEXT                                COMMENT '클레임 상세 내용',
    extracted_text  LONGTEXT                                COMMENT '업로드 파일 파싱 원문 (PDF/DOCX/EML)',
    claim_summary   TEXT                                    COMMENT 'LLM 생성 요약본',

    -- AI 분류 결과
    ai_defect_type  VARCHAR(50)                             COMMENT 'AI(CNN) 예측 불량 유형',
    ai_confidence   FLOAT                                   COMMENT 'AI 예측 신뢰도 (0.0 ~ 1.0)',
    llm_model       VARCHAR(100)                            COMMENT '사용 LLM 모델명 (Ollama 등)',

    -- 담당자
    handler         VARCHAR(100)                            COMMENT '담당자',
    author_name     VARCHAR(100)                            COMMENT '작성자',
    reviewer_name   VARCHAR(100)                            COMMENT '검토자',
    approver_name   VARCHAR(100)                            COMMENT '승인자',

    -- 대응 내용 (2단계 보고서 작성)
    root_cause_analysis TEXT                                COMMENT '원인 분석',
    corrective_action   TEXT                                COMMENT '시정 조치',
    preventive_action   TEXT                                COMMENT '재발 방지 대책',

    -- 상태
    report_status   VARCHAR(20) NOT NULL DEFAULT 'draft'   COMMENT '보고서 상태 (draft/submitted/approved/rejected)',

    -- 제약 / 인덱스
    FOREIGN KEY (defect_type) REFERENCES defect_types(code),
    INDEX idx_reports_status_id  (report_status, report_id),
    INDEX idx_reports_similar    (report_status, defect_type, customer_name, report_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='불량 보고서';


-- ------------------------------------------------------------
--  4. defect_report_images
--     보고서 첨부 이미지
--     report_id ON DELETE CASCADE → 보고서 삭제 시 이미지도 삭제
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS defect_report_images (
    image_id          INT          PRIMARY KEY AUTO_INCREMENT  COMMENT '이미지 고유 ID',
    report_id         INT          NOT NULL                    COMMENT 'FK → defect_reports',
    image_type        VARCHAR(100)                             COMMENT '이미지 종류 (불량부위 등)',
    image_path        VARCHAR(500) NOT NULL                    COMMENT '서버 파일 경로 (/uploads/...)',
    image_description TEXT                                     COMMENT '이미지 설명',
    defect_bbox       JSON                                     COMMENT 'AI 탐지 바운딩박스 (미사용)',
    uploaded_at       DATETIME     DEFAULT NOW()               COMMENT '업로드 시각',

    FOREIGN KEY (report_id) REFERENCES defect_reports(report_id)
        ON DELETE CASCADE,
    INDEX idx_images_report (report_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='보고서 첨부 이미지';
