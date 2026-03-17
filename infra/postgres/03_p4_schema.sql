-- P4: issues pipeline schema (raw_issues, normalized_issues, enriched_issues)
-- Выполняется под postgres в БД llm_gate

-- Используем llm_gate_admin, чтобы сработали default privileges из 02_schema.sql
SET ROLE llm_gate_admin;

-- ====================== Таблицы P4 ======================

CREATE TABLE IF NOT EXISTS llm.raw_issues (
  id             SERIAL PRIMARY KEY,
  source         TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload_json   JSONB NOT NULL,
  CONSTRAINT uq_raw_issues_source_payload_id
    UNIQUE (source, (payload_json->>'id'))
);

CREATE TABLE IF NOT EXISTS llm.normalized_issues (
  id             INT PRIMARY KEY,
  title          TEXT NOT NULL,
  description    TEXT,
  created_at     TIMESTAMPTZ,
  author         TEXT
);

CREATE TABLE IF NOT EXISTS llm.enriched_issues (
  id                 INT PRIMARY KEY REFERENCES llm.normalized_issues(id) ON DELETE CASCADE,
  label              TEXT NOT NULL,
  priority           TEXT,
  requires_backend   BOOLEAN NOT NULL DEFAULT FALSE,
  requires_frontend  BOOLEAN NOT NULL DEFAULT FALSE,
  entities           JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary            TEXT,
  confidence         DOUBLE PRECISION,
  processed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ====================== Allowlist ======================

INSERT INTO llm.sql_allowlist(schema_name, table_name, comment)
VALUES
  ('llm', 'raw_issues', 'P4: raw issues payloads'),
  ('llm', 'normalized_issues', 'P4: normalized issues'),
  ('llm', 'enriched_issues', 'P4: LLM-enriched issues')
ON CONFLICT (schema_name, table_name) DO UPDATE
SET is_enabled = EXCLUDED.is_enabled,
    comment    = EXCLUDED.comment;

-- Возвращаем роль
RESET ROLE;

