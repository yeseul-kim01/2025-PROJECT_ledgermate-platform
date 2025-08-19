-- 파일/원본 보관(공통)
CREATE TABLE IF NOT EXISTS artifact (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id        TEXT      NOT NULL,
  kind          TEXT      NOT NULL,     -- 'raw_pdf' | 'parse_json' | 'template' | ...
  filename      TEXT      NOT NULL,
  mime          TEXT,
  size_bytes    BIGINT,
  sha256        TEXT      NOT NULL,
  storage_path  TEXT      NOT NULL,     -- 저장소 내 상대경로
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, sha256, kind)
);
CREATE INDEX IF NOT EXISTS idx_artifact_org ON artifact(org_id);

-- 예산안 메타
CREATE TABLE IF NOT EXISTS budget_doc (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       TEXT      NOT NULL,
  title        TEXT,
  period_from  DATE,
  period_to    DATE,
  policy_id    UUID REFERENCES policy(id),   -- (선택) 해당 규정 버전과 연결
  source_pdf   UUID REFERENCES artifact(id),
  parsed_json  UUID REFERENCES artifact(id), -- 파싱 결과 JSON artifact
  created_by   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_budget_org ON budget_doc(org_id);

-- 예산/결산 상세 라인(나중에 파싱해서 구조화할 때 사용)
CREATE TABLE IF NOT EXISTS budget_line (
  id         BIGSERIAL PRIMARY KEY,
  budget_id  UUID NOT NULL REFERENCES budget_doc(id) ON DELETE CASCADE,
  line_no    INT,
  code       TEXT,                -- 100/510/611 등 분류코드
  category   TEXT,                -- 사업분야
  subcat     TEXT,                -- 세부 사업분야
  item       TEXT,                -- 비목/세부내역
  amount     NUMERIC(18,2),
  currency   TEXT DEFAULT 'KRW',
  notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_budget_line_budget ON budget_line(budget_id);
CREATE INDEX IF NOT EXISTS idx_budget_line_code   ON budget_line(code);

-- 결산안/예산안 양식(템플릿) 저장
CREATE TABLE IF NOT EXISTS form_template (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id        TEXT NOT NULL,
  kind          TEXT NOT NULL,         -- 'budget' | 'settlement'
  name          TEXT NOT NULL,
  version       TEXT NOT NULL,
  schema_json   JSONB NOT NULL,        -- 열/필드 정의(JSON Schema 비슷하게)
  sample_artifact UUID REFERENCES artifact(id),  -- 샘플 PDF/이미지(선택)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, kind, name, version)
);
CREATE INDEX IF NOT EXISTS idx_form_tpl_org ON form_template(org_id);

-- 예산문서 청크
CREATE TABLE IF NOT EXISTS budget_chunk (
  id            BIGSERIAL PRIMARY KEY,
  budget_doc_id BIGINT NOT NULL REFERENCES budget_doc(id) ON DELETE CASCADE,
  policy_id     UUID,                              -- policy와 연결되면 채우기 (옵션)
  org_id        TEXT  NOT NULL,                    -- 조인/필터 편의
  ord           INT   NOT NULL,                    -- 원문 순서 (order → ord 매핑)
  code          TEXT,                              -- 조항/섹션 코드(있으면)
  title         TEXT,                              -- 섹션/항목 제목
  path          TEXT,                              -- 섹션 경로( > 로 join된 문자열 등)
  text          TEXT NOT NULL,                     -- 검색 대상
  context_text  TEXT,                              -- 앞뒤 문맥(선택)
  tables_json   JSONB,                             -- 표 원본(옵션)
  meta          JSONB DEFAULT '{}'::jsonb,         -- 페이지/좌표 등 추가 메타
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 조회 성능용 인덱스
CREATE INDEX IF NOT EXISTS idx_budget_chunk_doc_ord
  ON budget_chunk (budget_doc_id, ord);

CREATE INDEX IF NOT EXISTS idx_budget_chunk_org
  ON budget_chunk (org_id);

-- (선택) 본문 검색용
-- CREATE INDEX IF NOT EXISTS idx_budget_chunk_fts
--   ON budget_chunk USING GIN (to_tsvector('simple', text));
