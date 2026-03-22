-- Роли и пользователи (суперпользователь postgres в БД llm_gate)

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_gate_owner') THEN
    CREATE ROLE llm_gate_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_gate_app') THEN
    CREATE ROLE llm_gate_app NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_gate_ro') THEN
    CREATE ROLE llm_gate_ro NOLOGIN;
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_gate_admin') THEN
    CREATE USER llm_gate_admin WITH PASSWORD 'CHANGE_ME_admin_password';
    GRANT llm_gate_owner TO llm_gate_admin;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_gate_service') THEN
    CREATE USER llm_gate_service WITH PASSWORD 'CHANGE_ME_service_password';
    GRANT llm_gate_app TO llm_gate_service;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'llm_gate_readonly') THEN
    CREATE USER llm_gate_readonly WITH PASSWORD 'CHANGE_ME_readonly_password';
    GRANT llm_gate_ro TO llm_gate_readonly;
  END IF;
END$$;

ALTER DATABASE llm_gate OWNER TO llm_gate_admin;
