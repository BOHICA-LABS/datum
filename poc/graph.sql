-- Full spec relationship graph.
--
-- Every edge below is read from REAL frontmatter keys in the live corpus:
--   BC:    subsystem, capability, lifecycle_status, replacement, deprecated_by
--   VP:    bcs[], domain_invariants[], nfrs[], source_bc, scope, module, proof_method
--   STORY: epic_id, depends_on[], blocks[], behavioral_contracts[],
--          verification_properties[], functional_requirements[], subsystems[]
--
-- Design rule: an edge is a ROW with FKs on both ends. A reference to a
-- non-existent node is then unrepresentable rather than "caught by a grep sweep".

-- ---------------------------------------------------------------- nodes

CREATE TABLE IF NOT EXISTS capability (
  cap_id      VARCHAR(16)  NOT NULL,        -- CAP-NNN
  name        TEXT         NULL,
  PRIMARY KEY (cap_id)
);

CREATE TABLE IF NOT EXISTS domain_invariant (
  di_id       VARCHAR(16)  NOT NULL,        -- DI-NNN
  name        TEXT         NULL,
  PRIMARY KEY (di_id)
);

CREATE TABLE IF NOT EXISTS nfr (
  nfr_id      VARCHAR(32)  NOT NULL,        -- NFR-SCALE-001
  name        TEXT         NULL,
  PRIMARY KEY (nfr_id)
);

CREATE TABLE IF NOT EXISTS fr (
  fr_id       VARCHAR(16)  NOT NULL,        -- FR-NNN
  name        TEXT         NULL,
  PRIMARY KEY (fr_id)
);

CREATE TABLE IF NOT EXISTS adr (
  adr_id      VARCHAR(16)  NOT NULL,        -- ADR-NNN
  title       TEXT         NULL,
  PRIMARY KEY (adr_id)
);

CREATE TABLE IF NOT EXISTS epic (
  epic_id     VARCHAR(16)  NOT NULL,        -- E-NN
  title       TEXT         NULL,
  PRIMARY KEY (epic_id)
);

-- ------------------------------------------------- node attribute columns

-- BC gains its real lifecycle fields. `replacement` is a self-FK: a BC that
-- claims to be replaced by a BC that does not exist is now impossible.
ALTER TABLE bc ADD COLUMN lifecycle_status VARCHAR(24) NULL;
ALTER TABLE bc ADD COLUMN replacement      VARCHAR(24) NULL;
ALTER TABLE bc ADD COLUMN status           VARCHAR(24) NULL;

ALTER TABLE vp ADD COLUMN scope        VARCHAR(8)  NULL;   -- SS-NN
ALTER TABLE vp ADD COLUMN source_bc    VARCHAR(24) NULL;
ALTER TABLE vp ADD COLUMN proof_method VARCHAR(32) NULL;
ALTER TABLE vp ADD COLUMN feasibility  VARCHAR(32) NULL;
ALTER TABLE vp ADD COLUMN module       TEXT        NULL;
ALTER TABLE vp ADD COLUMN vp_type      VARCHAR(32) NULL;

ALTER TABLE story ADD COLUMN epic_id  VARCHAR(16) NULL;
ALTER TABLE story ADD COLUMN priority VARCHAR(8)  NULL;
ALTER TABLE story ADD COLUMN points   VARCHAR(8)  NULL;
ALTER TABLE story ADD COLUMN cycle    VARCHAR(64) NULL;

-- ---------------------------------------------------------------- edges

-- VP -> BC (M:N). This is the table that was EMPTY in the first POC pass.
CREATE TABLE IF NOT EXISTS vp_bc (
  vp_id  VARCHAR(16) NOT NULL,
  bc_id  VARCHAR(24) NOT NULL,
  PRIMARY KEY (vp_id, bc_id),
  CONSTRAINT fk_vpbc_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE,
  CONSTRAINT fk_vpbc_bc FOREIGN KEY (bc_id) REFERENCES bc (bc_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vp_di (
  vp_id  VARCHAR(16) NOT NULL,
  di_id  VARCHAR(16) NOT NULL,
  PRIMARY KEY (vp_id, di_id),
  CONSTRAINT fk_vpdi_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE,
  CONSTRAINT fk_vpdi_di FOREIGN KEY (di_id) REFERENCES domain_invariant (di_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vp_nfr (
  vp_id  VARCHAR(16) NOT NULL,
  nfr_id VARCHAR(32) NOT NULL,
  PRIMARY KEY (vp_id, nfr_id),
  CONSTRAINT fk_vpnfr_vp  FOREIGN KEY (vp_id)  REFERENCES vp (vp_id)   ON DELETE CASCADE,
  CONSTRAINT fk_vpnfr_nfr FOREIGN KEY (nfr_id) REFERENCES nfr (nfr_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_vp (
  story_id VARCHAR(32) NOT NULL,
  vp_id    VARCHAR(16) NOT NULL,
  PRIMARY KEY (story_id, vp_id),
  CONSTRAINT fk_svp_story FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
  CONSTRAINT fk_svp_vp    FOREIGN KEY (vp_id)    REFERENCES vp (vp_id)       ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_fr (
  story_id VARCHAR(32) NOT NULL,
  fr_id    VARCHAR(16) NOT NULL,
  PRIMARY KEY (story_id, fr_id),
  CONSTRAINT fk_sfr_story FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
  CONSTRAINT fk_sfr_fr    FOREIGN KEY (fr_id)    REFERENCES fr (fr_id)       ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS story_subsystem (
  story_id VARCHAR(32) NOT NULL,
  ss_id    VARCHAR(8)  NOT NULL,
  PRIMARY KEY (story_id, ss_id),
  CONSTRAINT fk_sss_story FOREIGN KEY (story_id) REFERENCES story (story_id)   ON DELETE CASCADE,
  CONSTRAINT fk_sss_ss    FOREIGN KEY (ss_id)    REFERENCES subsystem (ss_id)  ON DELETE CASCADE
);

-- Story dependency DAG. Self-referential M:N. `kind` distinguishes the two
-- directions the corpus records independently (depends_on and blocks), so the
-- POC can check whether they actually agree with each other.
CREATE TABLE IF NOT EXISTS story_dep (
  story_id  VARCHAR(32) NOT NULL,           -- the story declaring the edge
  dep_id    VARCHAR(32) NOT NULL,           -- the other end
  kind      VARCHAR(16) NOT NULL,           -- 'depends_on' | 'blocks'
  PRIMARY KEY (story_id, dep_id, kind),
  CONSTRAINT fk_sdep_a FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
  CONSTRAINT fk_sdep_b FOREIGN KEY (dep_id)   REFERENCES story (story_id) ON DELETE CASCADE
);

-- VP -> subsystem. `scope` is declared as a single subsystem but the corpus
-- also uses comma lists ("SS-01, SS-03"), so it is genuinely M:N.
CREATE TABLE IF NOT EXISTS vp_subsystem (
  vp_id  VARCHAR(16) NOT NULL,
  ss_id  VARCHAR(8)  NOT NULL,
  PRIMARY KEY (vp_id, ss_id),
  CONSTRAINT fk_vpss_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id)         ON DELETE CASCADE,
  CONSTRAINT fk_vpss_ss FOREIGN KEY (ss_id) REFERENCES subsystem (ss_id)  ON DELETE CASCADE
);
