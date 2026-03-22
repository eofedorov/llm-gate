-- Схема, расширения, таблицы, триггеры, гранты, начальные данные

CREATE SCHEMA IF NOT EXISTS llm AUTHORIZATION llm_gate_admin;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER DEFAULT PRIVILEGES FOR ROLE llm_gate_admin IN SCHEMA llm
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO llm_gate_app;
ALTER DEFAULT PRIVILEGES FOR ROLE llm_gate_admin IN SCHEMA llm
  GRANT USAGE, SELECT ON SEQUENCES TO llm_gate_app;
ALTER DEFAULT PRIVILEGES FOR ROLE llm_gate_admin IN SCHEMA llm
  GRANT SELECT ON TABLES TO llm_gate_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE llm_gate_admin IN SCHEMA llm
  GRANT USAGE, SELECT ON SEQUENCES TO llm_gate_ro;

GRANT USAGE ON SCHEMA llm TO llm_gate_app, llm_gate_ro;
GRANT CREATE ON SCHEMA llm TO llm_gate_owner;
GRANT ALL ON SCHEMA llm TO llm_gate_admin;
REVOKE ALL ON SCHEMA llm FROM PUBLIC;

SET ROLE llm_gate_admin;

CREATE TABLE IF NOT EXISTS llm.kb_documents (
  doc_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_key           TEXT NOT NULL,
  title             TEXT NOT NULL,
  doc_type          TEXT NOT NULL DEFAULT 'general',
  language          TEXT NOT NULL,
  version           TEXT NOT NULL DEFAULT 'v1',
  sha256            TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT uq_kb_documents_doc_key UNIQUE (doc_key)
);
CREATE INDEX IF NOT EXISTS ix_kb_documents_doc_type
  ON llm.kb_documents (doc_type);

CREATE TABLE IF NOT EXISTS llm.kb_chunks (
  chunk_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id            UUID NOT NULL REFERENCES llm.kb_documents(doc_id) ON DELETE CASCADE,
  chunk_index       INT  NOT NULL,
  section           TEXT,
  text              TEXT NOT NULL,
  text_tokens_est   INT  NOT NULL DEFAULT 0,
  embedding_ref     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_kb_chunks_doc_index UNIQUE (doc_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_doc_id ON llm.kb_chunks (doc_id);

CREATE TABLE IF NOT EXISTS llm.runs (
  run_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_type          TEXT NOT NULL,
  request_id        TEXT,
  user_query        TEXT,
  status            TEXT NOT NULL DEFAULT 'started',
  model             TEXT,
  temperature       NUMERIC(4,3),
  max_tokens        INT,
  tokens_in         INT NOT NULL DEFAULT 0,
  tokens_out        INT NOT NULL DEFAULT 0,
  cost_usd          NUMERIC(12,6) NOT NULL DEFAULT 0,
  error_code        TEXT,
  error_message     TEXT,
  started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at       TIMESTAMPTZ,
  meta              JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_runs_started_at ON llm.runs (started_at DESC);
CREATE INDEX IF NOT EXISTS ix_runs_status ON llm.runs (status);

CREATE TABLE IF NOT EXISTS llm.run_retrievals (
  run_id            UUID NOT NULL REFERENCES llm.runs(run_id) ON DELETE CASCADE,
  chunk_id          UUID NOT NULL REFERENCES llm.kb_chunks(chunk_id) ON DELETE RESTRICT,
  rank              INT  NOT NULL,
  score             NUMERIC(12,6),
  used_in_context   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, chunk_id)
);
CREATE INDEX IF NOT EXISTS ix_run_retrievals_run_rank ON llm.run_retrievals (run_id, rank);

CREATE TABLE IF NOT EXISTS llm.tool_calls (
  tool_call_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id            UUID NOT NULL REFERENCES llm.runs(run_id) ON DELETE CASCADE,
  tool_name         TEXT NOT NULL,
  args              JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_meta       JSONB NOT NULL DEFAULT '{}'::jsonb,
  status            TEXT NOT NULL DEFAULT 'ok',
  error_message     TEXT,
  duration_ms       INT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tool_calls_run_id ON llm.tool_calls (run_id);
CREATE INDEX IF NOT EXISTS ix_tool_calls_tool_name ON llm.tool_calls (tool_name);

CREATE TABLE IF NOT EXISTS llm.sql_allowlist (
  allowlist_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  schema_name       TEXT NOT NULL DEFAULT 'llm',
  table_name        TEXT NOT NULL,
  is_enabled        BOOLEAN NOT NULL DEFAULT TRUE,
  comment           TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_sql_allowlist UNIQUE (schema_name, table_name)
);

CREATE OR REPLACE FUNCTION llm.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_kb_documents_updated_at ON llm.kb_documents;
CREATE TRIGGER trg_kb_documents_updated_at
BEFORE UPDATE ON llm.kb_documents
FOR EACH ROW EXECUTE FUNCTION llm.set_updated_at();

RESET ROLE;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA llm TO llm_gate_app;
GRANT SELECT ON ALL TABLES IN SCHEMA llm TO llm_gate_ro;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA llm TO llm_gate_app, llm_gate_ro;

INSERT INTO llm.sql_allowlist(schema_name, table_name, comment)
VALUES
  ('llm', 'kb_documents', 'Read-only: KB documents registry'),
  ('llm', 'kb_chunks', 'Read-only: KB chunks'),
  ('llm', 'runs', 'Read-only: runs telemetry'),
  ('llm', 'run_retrievals', 'Read-only: retrieval audit'),
  ('llm', 'tool_calls', 'Read-only: tool calls audit')
ON CONFLICT (schema_name, table_name) DO UPDATE
SET is_enabled = EXCLUDED.is_enabled, comment = EXCLUDED.comment;
