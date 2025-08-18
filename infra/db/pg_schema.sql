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
