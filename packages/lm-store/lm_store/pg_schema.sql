-- 확장 (선택)
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- 키워드 검색용
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- uuid_generate_v4()

-- 조직별 정책 메타
CREATE TABLE IF NOT EXISTS policy (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id          TEXT      NOT NULL,             -- 테넌트
  version         TEXT      NOT NULL,             -- 고객이 주는 버전/레이블
  source_name     TEXT      NOT NULL,             -- 파일명/출처
  sha256          TEXT      NOT NULL,             -- 원본/RAW 해시(중복 방지)
  effective_from  TIMESTAMPTZ,
  effective_to    TIMESTAMPTZ,
  supersedes_id   UUID REFERENCES policy(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(org_id, sha256)                          -- 동일 원본 중복 방지
);

-- 규정 청크
CREATE TABLE IF NOT EXISTS rule_chunk (
  id            BIGSERIAL PRIMARY KEY,
  policy_id     UUID  NOT NULL REFERENCES policy(id) ON DELETE CASCADE,
  org_id        TEXT  NOT NULL,                   -- 조인/필터 편의
  ord           INT   NOT NULL,                   -- 원문 순서
  code          TEXT,
  title         TEXT,
  path          TEXT,
  text          TEXT   NOT NULL,                  -- 검색 대상
  context_text  TEXT,
  tables_json   JSONB,                            -- 표 원본(옵션)
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_policy_org ON policy(org_id);
CREATE INDEX IF NOT EXISTS idx_chunk_policy ON rule_chunk(policy_id);
CREATE INDEX IF NOT EXISTS idx_chunk_org ON rule_chunk(org_id);

-- 텍스트 검색 가속(한국어 섞임 → trgm이 간편)
CREATE INDEX IF NOT EXISTS idx_chunk_text_trgm ON rule_chunk USING gin (text gin_trgm_ops);

-- RLS 스켈레톤: 세션 변수 app.org_id 로 테넌트 격리
ALTER TABLE policy     ENABLE ROW LEVEL SECURITY;
ALTER TABLE rule_chunk ENABLE ROW LEVEL SECURITY;
CREATE POLICY policy_rls     ON policy
  USING (org_id = current_setting('app.org_id', true));
CREATE POLICY rule_chunk_rls ON rule_chunk
  USING (org_id = current_setting('app.org_id', true));
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




-- settlement_template 테이블(최소 필드)
CREATE TABLE IF NOT EXISTS settlement_template (
  template_id TEXT PRIMARY KEY,          -- file_id_of(pdf_path)
  file_path   TEXT NOT NULL,
  schema_json JSONB NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);


-- psql -h $PG_HOST -U $PG_USER -d $PG_DB 로 접속 후 실행
CREATE EXTENSION IF NOT EXISTS vector;

-- 세칙(정책) 청크 저장소
DROP TABLE IF EXISTS policy_chunks;
CREATE TABLE policy_chunks (
  id BIGSERIAL PRIMARY KEY,
  doc_title TEXT,
  version TEXT,
  section TEXT,
  page INT,
  snippet TEXT,
  embedding vector(1536)  -- EMBED_DIM과 동일해야 함
);
CREATE INDEX IF NOT EXISTS idx_policy_chunks_vec ON policy_chunks USING hnsw (embedding vector_cosine_ops);

-- 예산 라인 저장소
DROP TABLE IF EXISTS budget_lines;
CREATE TABLE budget_lines (
  id BIGSERIAL PRIMARY KEY,
  line_title TEXT,
  line_code TEXT,
  category_path TEXT,
  remaining_amount NUMERIC,
  embedding vector(1536)  -- EMBED_DIM과 동일해야 함
);
CREATE INDEX IF NOT EXISTS idx_budget_lines_vec ON budget_lines USING hnsw (embedding vector_cosine_ops);
