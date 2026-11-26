-- Eurogas Nexus: separate PostgreSQL roles (security review H5).
--
-- Run once as a superuser (or the database owner) after the first `alembic upgrade head`,
-- with psql variables for the passwords, for example:
--
--   psql "$ADMIN_URL" -v owner_password="'...'" -v app_password="'...'" \
--        -v reader_password="'...'" -v db=eurogas -f deploy/runtime/database_roles.sql
--
-- Roles:
--   eurogas_owner   owns the schema; runs migrations (compose service `migrate`) and the
--                   dual-controlled audit prune. Never used by the running services.
--   eurogas_app     the API and the workers: read and write business tables, INSERT-only on
--                   the audit trail (no UPDATE, DELETE or TRUNCATE), no DDL.
--   eurogas_reader  read-only reporting (Excel, BI, a replica).
--   eurogas_auditor compliance exports: reads the audit trail only.
--
-- Then set EUROGAS_NEXUS_OWNER_DB_USER/_PASSWORD and EUROGAS_NEXUS_APP_DB_USER/_PASSWORD in
-- the compose environment file (docs/security/DATABASE_ROLES.md).

\set ON_ERROR_STOP on

CREATE ROLE eurogas_owner LOGIN PASSWORD :owner_password;
CREATE ROLE eurogas_app LOGIN PASSWORD :app_password;
CREATE ROLE eurogas_reader LOGIN PASSWORD :reader_password;
CREATE ROLE eurogas_auditor NOLOGIN;

-- Hand the existing schema to the owner role (it was created by POSTGRES_USER).
REASSIGN OWNED BY CURRENT_USER TO eurogas_owner;
ALTER DATABASE :db OWNER TO eurogas_owner;
ALTER SCHEMA public OWNER TO eurogas_owner;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO eurogas_app, eurogas_reader, eurogas_auditor;

SET ROLE eurogas_owner;

-- The application: data manipulation only.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO eurogas_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO eurogas_app;
-- The audit trail is append-only for the application.
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events, audit_chain, audit_chain_anchors FROM eurogas_app;
GRANT SELECT, INSERT ON audit_events, audit_chain, audit_chain_anchors TO eurogas_app;
-- Schema changes are the owner's.
REVOKE TRUNCATE ON ALL TABLES IN SCHEMA public FROM eurogas_app;

-- Reporting reads everything except credentials and the second-factor store.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO eurogas_reader;
REVOKE SELECT ON identity_local_credentials, identity_mfa, provider_credentials,
    identity_api_keys, user_sessions FROM eurogas_reader;

GRANT SELECT ON audit_events, audit_chain, audit_chain_anchors TO eurogas_auditor;

-- Tables a later migration creates get the same grants.
ALTER DEFAULT PRIVILEGES FOR ROLE eurogas_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO eurogas_app;
ALTER DEFAULT PRIVILEGES FOR ROLE eurogas_owner IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO eurogas_app;
ALTER DEFAULT PRIVILEGES FOR ROLE eurogas_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO eurogas_reader;

RESET ROLE;
