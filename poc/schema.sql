-- factory-artifacts schema (POC)
-- Design principle: every count, index, and cross-reference that the current
-- markdown corpus maintains BY HAND becomes a derived query or a DB constraint.
-- Nothing that can drift is stored twice.

CREATE TABLE IF NOT EXISTS subsystem (
  ss_id       VARCHAR(8)   NOT NULL,        -- SS-01
  bc_prefix   INT          NOT NULL,        -- 1..10
  name        VARCHAR(200) NOT NULL,
  PRIMARY KEY (ss_id),
  UNIQUE KEY uk_bc_prefix (bc_prefix)
);

-- Behavioral contracts. 1 row per BC. The ONLY place a BC exists.
-- BC-INDEX.md and the per-subsystem counts become SELECTs, not files.
CREATE TABLE IF NOT EXISTS bc (
  bc_id       VARCHAR(24)  NOT NULL,        -- BC-S.SS.NNN
  ss_id       VARCHAR(8)   NOT NULL,        -- authoritative subsystem (frontmatter, not directory)
  title       TEXT         NOT NULL,
  body        LONGTEXT     NOT NULL,
  capability  VARCHAR(32)  NULL,            -- CAP-008 etc; NULL = genuinely unassigned
  version     VARCHAR(16)  NOT NULL DEFAULT 'v1.0',
  last_amended DATE        NULL,
  PRIMARY KEY (bc_id),
  KEY idx_bc_ss (ss_id),
  KEY idx_bc_cap (capability),
  CONSTRAINT fk_bc_ss FOREIGN KEY (ss_id) REFERENCES subsystem (ss_id)
);

CREATE TABLE IF NOT EXISTS vp (
  vp_id       VARCHAR(16)  NOT NULL,        -- VP-NNN
  title       TEXT         NOT NULL,
  body        LONGTEXT     NOT NULL,
  version     VARCHAR(16)  NOT NULL DEFAULT 'v1.0',
  PRIMARY KEY (vp_id)
);

CREATE TABLE IF NOT EXISTS story (
  story_id    VARCHAR(32)  NOT NULL,        -- S-12.04
  title       TEXT         NOT NULL,
  status      VARCHAR(24)  NOT NULL DEFAULT 'pending',
  wave        INT          NULL,
  body        LONGTEXT     NOT NULL,
  PRIMARY KEY (story_id),
  KEY idx_story_wave (wave),
  KEY idx_story_status (status)
);

-- Traceability. A dangling reference is now IMPOSSIBLE, not "caught by a grep sweep".
-- This is the table that makes the 3 dangling BC refs in the live corpus unrepresentable.
CREATE TABLE IF NOT EXISTS bc_trace (
  bc_id       VARCHAR(24)  NOT NULL,
  vp_id       VARCHAR(16)  NOT NULL,
  PRIMARY KEY (bc_id, vp_id),
  CONSTRAINT fk_trace_bc FOREIGN KEY (bc_id) REFERENCES bc (bc_id) ON DELETE CASCADE,
  CONSTRAINT fk_trace_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_bc (
  story_id    VARCHAR(32)  NOT NULL,
  bc_id       VARCHAR(24)  NOT NULL,
  PRIMARY KEY (story_id, bc_id),
  CONSTRAINT fk_sbc_story FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
  CONSTRAINT fk_sbc_bc    FOREIGN KEY (bc_id)    REFERENCES bc (bc_id)       ON DELETE CASCADE
);

-- Pipeline state. Scalar rows, not a 379-line markdown file re-read every session.
CREATE TABLE IF NOT EXISTS pipeline_state (
  k           VARCHAR(64)  NOT NULL,
  v           TEXT         NOT NULL,
  PRIMARY KEY (k)
);

CREATE TABLE IF NOT EXISTS phase (
  phase_id    VARCHAR(24)  NOT NULL,
  status      VARCHAR(24)  NOT NULL DEFAULT 'pending',
  verdict     VARCHAR(24)  NULL,
  findings    INT          NULL,
  PRIMARY KEY (phase_id)
);

-- The factory lock. Single row, CAS-updated in one transaction.
-- Replaces: a YAML block inside STATE.md + fetch + push --force-with-lease,
-- which has a documented TOCTOU window (CWE-367).
CREATE TABLE IF NOT EXISTS factory_lock (
  id          TINYINT      NOT NULL DEFAULT 1,
  holder      VARCHAR(200) NULL,            -- NULL = unlocked
  locked_at   DATETIME     NULL,
  expires_at  DATETIME     NULL,
  fence       BIGINT       NOT NULL DEFAULT 0,  -- monotonic; detects stale holders
  PRIMARY KEY (id),
  CONSTRAINT ck_lock_singleton CHECK (id = 1)
);
