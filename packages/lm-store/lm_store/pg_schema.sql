-- 0) 확장
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector

-- 1) 조직별 정책 메타
CREATE TABLE IF NOT EXISTS policy (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id          TEXT      NOT NULL,
  version         TEXT      NOT NULL,
  source_name     TEXT      NOT NULL,
  sha256          TEXT      NOT NULL,
  effective_from  TIMESTAMPTZ,
  effective_to    TIMESTAMPTZ,
  supersedes_id   UUID REFERENCES policy(id),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(org_id, sha256)
);

-- 2) 규정 청크 (+ embeddings)
CREATE TABLE IF NOT EXISTS rule_chunk (
  id            BIGSERIAL PRIMARY KEY,
  policy_id     UUID  NOT NULL REFERENCES policy(id) ON DELETE CASCADE,
  org_id        TEXT  NOT NULL,
  ord           INT   NOT NULL,
  code          TEXT,
  title         TEXT,
  path          TEXT,
  text          TEXT   NOT NULL,
  context_text  TEXT,
  tables_json   JSONB,
  embedding     vector(4096),   -- 원본 4096
  embedding_i2000 vector(2000), -- 검색용 축소본 2000
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3) 파일/원본 보관
CREATE TABLE IF NOT EXISTS artifact (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id        TEXT      NOT NULL,
  kind          TEXT      NOT NULL, -- 'raw_pdf' | 'parse_json' | 'template' | ...
  filename      TEXT      NOT NULL,
  mime          TEXT,
  size_bytes    BIGINT,
  sha256        TEXT      NOT NULL,
  storage_path  TEXT      NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, sha256, kind)
);

-- 4) 예산안 메타
CREATE TABLE IF NOT EXISTS budget_doc (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       TEXT      NOT NULL,
  title        TEXT,
  period_from  DATE,
  period_to    DATE,
  policy_id    UUID REFERENCES policy(id),
  source_pdf   UUID REFERENCES artifact(id),
  parsed_json  UUID REFERENCES artifact(id),
  created_by   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5) 예산 상세 라인 (+ embeddings)
CREATE TABLE IF NOT EXISTS budget_line (
  id         BIGSERIAL PRIMARY KEY,
  budget_id  UUID NOT NULL REFERENCES budget_doc(id) ON DELETE CASCADE,
  line_no    INT,
  code       TEXT,
  category   TEXT,
  subcat     TEXT,
  item       TEXT,
  amount     NUMERIC(18,2),
  currency   TEXT DEFAULT 'KRW',
  notes      TEXT,
  embedding  vector(4096),    -- 원본 4096
  embedding_i2000 vector(2000) -- 검색용 축소본 2000
);

-- 6) 템플릿들
CREATE TABLE IF NOT EXISTS form_template (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id        TEXT NOT NULL,
  kind          TEXT NOT NULL,   -- 'budget' | 'settlement'
  name          TEXT NOT NULL,
  version       TEXT NOT NULL,
  schema_json   JSONB NOT NULL,
  sample_artifact UUID REFERENCES artifact(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, kind, name, version)
);

CREATE TABLE IF NOT EXISTS settlement_template (
  template_id TEXT PRIMARY KEY,
  file_path   TEXT NOT NULL,
  schema_json JSONB NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

-- 7) 일반 인덱스
CREATE INDEX IF NOT EXISTS idx_policy_org         ON policy(org_id);
CREATE INDEX IF NOT EXISTS idx_chunk_policy       ON rule_chunk(policy_id);
CREATE INDEX IF NOT EXISTS idx_chunk_org          ON rule_chunk(org_id);
CREATE INDEX IF NOT EXISTS idx_chunk_text_trgm    ON rule_chunk USING gin (text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_artifact_org       ON artifact(org_id);
CREATE INDEX IF NOT EXISTS idx_budget_org         ON budget_doc(org_id);
CREATE INDEX IF NOT EXISTS idx_budget_line_budget ON budget_line(budget_id);
CREATE INDEX IF NOT EXISTS idx_budget_line_code   ON budget_line(code);

-- 7-1) 벡터 인덱스 (중요: 2000 축소본에만 HNSW)
CREATE INDEX IF NOT EXISTS idx_rule_chunk_i2000_hnsw
  ON rule_chunk USING hnsw (embedding_i2000 vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_budget_line_i2000_hnsw
  ON budget_line USING hnsw (embedding_i2000 vector_cosine_ops);

-- 8) 멀티테넌트 RLS
ALTER TABLE policy     ENABLE ROW LEVEL SECURITY;
ALTER TABLE rule_chunk ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='policy' AND policyname='policy_rls'
  ) THEN
    CREATE POLICY policy_rls ON policy
      USING (org_id = current_setting('app.org_id', true));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='rule_chunk' AND policyname='rule_chunk_rls'
  ) THEN
    CREATE POLICY rule_chunk_rls ON rule_chunk
      USING (org_id = current_setting('app.org_id', true));
  END IF;
END$$;
