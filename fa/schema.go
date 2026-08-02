package main

// The schema, as statements rather than a .sql file: `fa` is one binary and must
// carry its own DDL (no data files to lose, no path to get wrong).
//
// Design rules it encodes (SPEC §2):
//   1. No count is ever stored. Counts are COUNT(*). This is what makes the
//      corpus's current four-way BC total (1949/1955/1959/1962) unrepresentable.
//   2. Every cross-reference is a row with FKs on BOTH ends, so a dangling
//      reference is refused at write time instead of being hunted by a grep sweep.
//   3. Cross-machine counters are append-only rows, never mutable cells.
//   5. Nothing derivable is stored.
//
// The one deliberate exception to rule 2 is `corpus_assertion`: it records what
// the MARKDOWN claims, precisely so a gate can compare those claims against
// COUNT(*). Recording a wrong number is the point of that table.

const schemaVersion = 4

// openDDL is the `open` zone: specs, stories, waves, state — what most agents read.
var openDDL = []string{
	`CREATE TABLE IF NOT EXISTS subsystem (
	  ss_id      VARCHAR(8)   NOT NULL,
	  bc_prefix  INT          NOT NULL,
	  name       VARCHAR(200) NOT NULL,
	  PRIMARY KEY (ss_id),
	  UNIQUE KEY uk_bc_prefix (bc_prefix)
	)`,

	// Node universes. Each comes from its AUTHORITATIVE declaring document only
	// (capabilities.md, invariants.md, the phase-0 NFR catalog, prd.md, ADR
	// headings, stories/epics/). Building them from grep-over-everything would
	// make every reference resolve trivially and prove nothing.
	`CREATE TABLE IF NOT EXISTS capability (
	  cap_id VARCHAR(16) NOT NULL, name TEXT NULL, PRIMARY KEY (cap_id))`,
	`CREATE TABLE IF NOT EXISTS domain_invariant (
	  di_id VARCHAR(16) NOT NULL, name TEXT NULL, PRIMARY KEY (di_id))`,
	`CREATE TABLE IF NOT EXISTS nfr (
	  nfr_id VARCHAR(32) NOT NULL, name TEXT NULL, PRIMARY KEY (nfr_id))`,
	`CREATE TABLE IF NOT EXISTS fr (
	  fr_id VARCHAR(32) NOT NULL, name TEXT NULL, PRIMARY KEY (fr_id))`,
	`CREATE TABLE IF NOT EXISTS adr (
	  adr_id VARCHAR(16) NOT NULL, title TEXT NULL, PRIMARY KEY (adr_id))`,
	`CREATE TABLE IF NOT EXISTS epic (
	  epic_id VARCHAR(16) NOT NULL, title TEXT NULL, PRIMARY KEY (epic_id))`,

	`CREATE TABLE IF NOT EXISTS bc (
	  bc_id            VARCHAR(24)  NOT NULL,
	  ss_id            VARCHAR(8)   NOT NULL,
	  title            TEXT         NOT NULL,
	  body             LONGTEXT     NOT NULL,
	  capability       VARCHAR(32)  NULL,
	  version          VARCHAR(16)  NOT NULL DEFAULT 'v1.0',
	  lifecycle_status VARCHAR(24)  NULL,
	  status           VARCHAR(24)  NULL,
	  replacement      VARCHAR(24)  NULL,
	  src_path         VARCHAR(512) NULL,
	  PRIMARY KEY (bc_id),
	  KEY idx_bc_ss (ss_id),
	  KEY idx_bc_cap (capability),
	  CONSTRAINT fk_bc_ss FOREIGN KEY (ss_id) REFERENCES subsystem (ss_id)
	)`,

	`CREATE TABLE IF NOT EXISTS vp (
	  vp_id        VARCHAR(16)  NOT NULL,
	  title        TEXT         NOT NULL,
	  body         LONGTEXT     NOT NULL,
	  version      VARCHAR(16)  NOT NULL DEFAULT 'v1.0',
	  scope        VARCHAR(8)   NULL,
	  source_bc    VARCHAR(24)  NULL,
	  proof_method VARCHAR(64)  NULL,
	  feasibility  VARCHAR(64)  NULL,
	  module       TEXT         NULL,
	  vp_type      VARCHAR(64)  NULL,
	  src_path     VARCHAR(512) NULL,
	  PRIMARY KEY (vp_id)
	)`,

	`CREATE TABLE IF NOT EXISTS story (
	  story_id VARCHAR(32)  NOT NULL,
	  title    TEXT         NOT NULL,
	  status   VARCHAR(24)  NOT NULL DEFAULT 'pending',
	  wave     INT          NULL,
	  epic_id  VARCHAR(16)  NULL,
	  priority VARCHAR(8)   NULL,
	  points   VARCHAR(8)   NULL,
	  cycle    VARCHAR(64)  NULL,
	  body     LONGTEXT     NOT NULL,
	  src_path VARCHAR(512) NULL,
	  PRIMARY KEY (story_id),
	  KEY idx_story_wave (wave),
	  KEY idx_story_status (status)
	)`,

	// Edges. FKs on both ends: a dangling reference is refused, not swept for.
	`CREATE TABLE IF NOT EXISTS vp_bc (
	  vp_id VARCHAR(16) NOT NULL, bc_id VARCHAR(24) NOT NULL,
	  PRIMARY KEY (vp_id, bc_id),
	  CONSTRAINT fk_vpbc_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE,
	  CONSTRAINT fk_vpbc_bc FOREIGN KEY (bc_id) REFERENCES bc (bc_id) ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS vp_di (
	  vp_id VARCHAR(16) NOT NULL, di_id VARCHAR(16) NOT NULL,
	  PRIMARY KEY (vp_id, di_id),
	  CONSTRAINT fk_vpdi_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE,
	  CONSTRAINT fk_vpdi_di FOREIGN KEY (di_id) REFERENCES domain_invariant (di_id) ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS vp_nfr (
	  vp_id VARCHAR(16) NOT NULL, nfr_id VARCHAR(32) NOT NULL,
	  PRIMARY KEY (vp_id, nfr_id),
	  CONSTRAINT fk_vpnfr_vp  FOREIGN KEY (vp_id)  REFERENCES vp (vp_id)   ON DELETE CASCADE,
	  CONSTRAINT fk_vpnfr_nfr FOREIGN KEY (nfr_id) REFERENCES nfr (nfr_id) ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS vp_subsystem (
	  vp_id VARCHAR(16) NOT NULL, ss_id VARCHAR(8) NOT NULL,
	  PRIMARY KEY (vp_id, ss_id),
	  CONSTRAINT fk_vpss_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id)        ON DELETE CASCADE,
	  CONSTRAINT fk_vpss_ss FOREIGN KEY (ss_id) REFERENCES subsystem (ss_id) ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS story_bc (
	  story_id VARCHAR(32) NOT NULL, bc_id VARCHAR(24) NOT NULL,
	  PRIMARY KEY (story_id, bc_id),
	  CONSTRAINT fk_sbc_story FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
	  CONSTRAINT fk_sbc_bc    FOREIGN KEY (bc_id)    REFERENCES bc (bc_id)       ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS story_vp (
	  story_id VARCHAR(32) NOT NULL, vp_id VARCHAR(16) NOT NULL,
	  PRIMARY KEY (story_id, vp_id),
	  CONSTRAINT fk_svp_story FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
	  CONSTRAINT fk_svp_vp    FOREIGN KEY (vp_id)    REFERENCES vp (vp_id)       ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS story_fr (
	  story_id VARCHAR(32) NOT NULL, fr_id VARCHAR(32) NOT NULL,
	  PRIMARY KEY (story_id, fr_id),
	  CONSTRAINT fk_sfr_story FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
	  CONSTRAINT fk_sfr_fr    FOREIGN KEY (fr_id)    REFERENCES fr (fr_id)       ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS story_subsystem (
	  story_id VARCHAR(32) NOT NULL, ss_id VARCHAR(8) NOT NULL,
	  PRIMARY KEY (story_id, ss_id),
	  CONSTRAINT fk_sss_story FOREIGN KEY (story_id) REFERENCES story (story_id)  ON DELETE CASCADE,
	  CONSTRAINT fk_sss_ss    FOREIGN KEY (ss_id)    REFERENCES subsystem (ss_id) ON DELETE CASCADE)`,
	// The dependency DAG. `kind` keeps the two directions the corpus records
	// independently (depends_on and blocks) so a gate can check they agree.
	`CREATE TABLE IF NOT EXISTS story_dep (
	  story_id VARCHAR(32) NOT NULL, dep_id VARCHAR(32) NOT NULL, kind VARCHAR(16) NOT NULL,
	  PRIMARY KEY (story_id, dep_id, kind),
	  CONSTRAINT fk_sdep_a FOREIGN KEY (story_id) REFERENCES story (story_id) ON DELETE CASCADE,
	  CONSTRAINT fk_sdep_b FOREIGN KEY (dep_id)   REFERENCES story (story_id) ON DELETE CASCADE)`,
	`CREATE TABLE IF NOT EXISTS bc_trace (
	  bc_id VARCHAR(24) NOT NULL, vp_id VARCHAR(16) NOT NULL,
	  PRIMARY KEY (bc_id, vp_id),
	  CONSTRAINT fk_trace_bc FOREIGN KEY (bc_id) REFERENCES bc (bc_id) ON DELETE CASCADE,
	  CONSTRAINT fk_trace_vp FOREIGN KEY (vp_id) REFERENCES vp (vp_id) ON DELETE CASCADE)`,

	// What the markdown CLAIMS about itself. The only table that stores a count,
	// and it exists so `fa validate` can catch the claim disagreeing with reality.
	// source/subject widened at schema v2: story 4's review claims are keyed by the review's
	// corpus-relative PATH (reviews carry no declared id yet), which does not fit 64 chars.
	// The PK is (source, kind, subject) = 664 chars = 2,656 bytes at utf8mb4, inside the
	// 3,072-byte index limit — checked rather than assumed, because an over-long PK fails at
	// CREATE time and would look like a schema bug rather than a sizing one.
	`CREATE TABLE IF NOT EXISTS corpus_assertion (
	  source    VARCHAR(300) NOT NULL,
	  kind      VARCHAR(64)  NOT NULL,
	  subject   VARCHAR(300) NOT NULL,
	  claimed   BIGINT       NOT NULL,
	  src_path  VARCHAR(512) NULL,
	  PRIMARY KEY (source, kind, subject)
	)`,

	// What an index ENUMERATES, as distinct from what it COUNTS. Two different
	// claims that can fail independently: an index can list a BC that does not
	// exist, and can omit one that does.
	`CREATE TABLE IF NOT EXISTS index_entry (
	  kind   VARCHAR(24)  NOT NULL,
	  id     VARCHAR(64)  NOT NULL,
	  source VARCHAR(200) NOT NULL,
	  PRIMARY KEY (kind, id, source)
	)`,

	// Findings the import path observes and the data therefore cannot show later:
	// a value that is not an id at all, an id with prose glued on, and every edge
	// a FOREIGN KEY refused (the row is gone, so only the import can report it).
	`CREATE TABLE IF NOT EXISTS finding (
	  rule        VARCHAR(200) NOT NULL,
	  subject     VARCHAR(400) NOT NULL,
	  class       VARCHAR(24)  NOT NULL,
	  detail      TEXT         NULL,
	  occurrences INT          NOT NULL DEFAULT 1,
	  PRIMARY KEY (rule, subject)
	)`,

	// STORY 4. A review document, and its findings AS ROWS.
	//
	// The `adversarial-finding` template exists and NOTHING uses it (measured: 0 files carry
	// that document_type), so finding_count / findings_total / severity_distribution are
	// authored numbers over prose. As rows they become COUNT(*) and GROUP BY, which is what
	// design rule 1 already requires of every other count in this schema.
	`CREATE TABLE IF NOT EXISTS review (
	  review_key VARCHAR(200) NOT NULL,
	  cycle      VARCHAR(120) NULL,
	  pass       INT          NULL,
	  target     TEXT         NULL,
	  src_path   VARCHAR(512) NULL,
	  PRIMARY KEY (review_key),
	  KEY idx_review_cycle (cycle)
	)`,

	// The natural key is COMPOSITE and scoped to the owning review, exactly as the template
	// declares — a finding id is not globally unique, the same discipline AC-NNN needs.
	//
	// `owned` distinguishes a finding this pass INTRODUCED from one it re-states to audit a
	// prior pass's fix. Without it a derived count counts mentions: measured 412
	// mentioned-not-owned rows, and counting them put adv-s8.08-p2 at 21 against a claimed 9.
	//
	// `sev_source` records WHICH of the six severity sources resolved the value, so an
	// unresolved severity is a measured fact rather than a silent parser default.
	`CREATE TABLE IF NOT EXISTS adversarial_finding (
	  review_key VARCHAR(200) NOT NULL,
	  finding_id VARCHAR(64)  NOT NULL,
	  severity   VARCHAR(8)   NULL,
	  sev_source VARCHAR(24)  NULL,
	  category   TEXT         NULL,   -- TEXT, not an enum: see the type finding in findings.go
	  statement  TEXT         NULL,
	  location   TEXT         NULL,
	  form       VARCHAR(16)  NOT NULL,
	  owned      TINYINT      NOT NULL DEFAULT 1,
	  src_line   INT          NULL,
	  PRIMARY KEY (review_key, finding_id),
	  KEY idx_af_sev (severity),
	  CONSTRAINT fk_af_review FOREIGN KEY (review_key) REFERENCES review (review_key) ON DELETE CASCADE
	)`,

	// STORY 12a. AC / EC / PC / T-task as rows, with TYPED links.
	//
	// The key is COMPOSITE and scoped to the owner, exactly as prose_ref_rules
	// scope-sub-artifact-ids requires: AC-002 is not globally unique, so identity is
	// (owner_key, kind, sub_id). The same discipline story 4 applied to finding ids.
	`CREATE TABLE IF NOT EXISTS sub_artifact (
	  owner_key  VARCHAR(64)  NOT NULL,
	  owner_type VARCHAR(32)  NOT NULL,
	  kind       VARCHAR(12)  NOT NULL,
	  sub_id     VARCHAR(24)  NOT NULL,
	  statement  TEXT         NULL,
	  form       VARCHAR(12)  NOT NULL,
	  src_line   INT          NULL,
	  PRIMARY KEY (owner_key, kind, sub_id),
	  KEY idx_sub_kind (kind)
	)`,

	// The typed link that turns a prose trace into a JOIN. `clause` keeps the sub-element the
	// trace names ("postcondition 1"), because the mis-anchor class is about WHICH clause and
	// not about whether the target exists.
	//
	// NO foreign key on target_id ON PURPOSE: the corpus traces to ids that do not exist, and
	// an FK would refuse the import and DESTROY the finding. Same call import.go already makes
	// for the reference-shaped scalar columns; gateSubArtifactRefsResolve reports them instead.
	`CREATE TABLE IF NOT EXISTS sub_artifact_ref (
	  owner_key   VARCHAR(64)  NOT NULL,
	  kind        VARCHAR(12)  NOT NULL,
	  sub_id      VARCHAR(24)  NOT NULL,
	  target_kind VARCHAR(12)  NOT NULL,
	  target_id   VARCHAR(64)  NOT NULL,
	  clause      VARCHAR(64)  NOT NULL DEFAULT '',
	  PRIMARY KEY (owner_key, kind, sub_id, target_kind, target_id, clause),
	  KEY idx_sar_target (target_kind, target_id),
	  CONSTRAINT fk_sar_sub FOREIGN KEY (owner_key, kind, sub_id)
	    REFERENCES sub_artifact (owner_key, kind, sub_id) ON DELETE CASCADE
	)`,

	// STORY 12b. The two reference kinds that genuinely cannot become rows: a section reference
	// points INTO a body, and a version cite is a claim about a target's state at a moment.
	//
	// `section_ord` is D-A's ordinal-keyed partition, so a resolved reference names the SECTION
	// rather than a 615 KB document. `status` keeps `unresolvable` DISTINCT from `dangling`,
	// which prose_ref_rules report-unresolvable-separately requires: collapsing them "is how a
	// prose extractor produces a large, confident, wrong finding set".
	`CREATE TABLE IF NOT EXISTS prose_ref (
	  citing_key  VARCHAR(300) NOT NULL,
	  citing_type VARCHAR(64)  NOT NULL,
	  kind        VARCHAR(16)  NOT NULL,
	  raw         VARCHAR(220) NOT NULL,
	  target      VARCHAR(220) NOT NULL,
	  section_ord INT          NOT NULL DEFAULT -1,
	  status      VARCHAR(16)  NOT NULL,
	  src_line    INT          NOT NULL,   -- part of the PK: the line distinguishes two refs
	  PRIMARY KEY (citing_key, kind, raw, src_line),
	  KEY idx_pr_status (status)
	)`,

	// The verdict is decided by PIN POLICY, never by whether the cite matches today: the same
	// syntax carries OPPOSITE verdicts. A `lagging-pinned-ok` row is CORRECT by design and the
	// gate deliberately does not report it.
	`CREATE TABLE IF NOT EXISTS version_cite (
	  citing_key    VARCHAR(300) NOT NULL,
	  citing_type   VARCHAR(64)  NOT NULL,
	  target        VARCHAR(64)  NOT NULL,
	  cited_version VARCHAR(16)  NOT NULL,
	  pin_policy    VARCHAR(12)  NOT NULL,
	  verdict       VARCHAR(24)  NOT NULL,
	  src_line      INT          NOT NULL,   -- part of the PK, same reason
	  PRIMARY KEY (citing_key, target, cited_version, src_line),
	  KEY idx_vc_verdict (verdict)
	)`,

	`CREATE TABLE IF NOT EXISTS schema_migrations (
	  version    INT          NOT NULL,
	  name       VARCHAR(200) NOT NULL,
	  applied_at DATETIME     NOT NULL,
	  PRIMARY KEY (version)
	)`,

	// Append-only import ledger (design rule 3: append-only rows, never a mutable
	// cell), so `fa doctor` and CI can say WHICH corpus state a store reflects.
	//
	// Keyed by a CONTENT fingerprint and holding no timestamp and no path on
	// purpose: a re-import of the same corpus must leave the working set byte
	// identical (W5 idempotence), and a clock or an absolute path would make every
	// run a change. Environment belongs in the log line, not in the data.
	`CREATE TABLE IF NOT EXISTS import_run (
	  fingerprint VARCHAR(64) NOT NULL,
	  fa_version  VARCHAR(32) NOT NULL,
	  n_bc        INT         NOT NULL,
	  n_vp        INT         NOT NULL,
	  n_story     INT         NOT NULL,
	  n_edge      INT         NOT NULL,
	  PRIMARY KEY (fingerprint)
	)`,
}

// walledDDL is the `walled` zone: artifacts some agents must be structurally
// unable to see (holdout scenarios, adversary expectations).
//
// hs_bc is the cross-zone reference that D2 costs us: splitting zones removes
// this FK, because the BC it points at lives in another database directory.
// `fa validate --cross-zone` buys that guarantee back in the tool (see D2:
// "a required deliverable, not an optional extra").
var walledDDL = []string{
	`CREATE TABLE IF NOT EXISTS holdout_scenario (
	  hs_id       VARCHAR(16)  NOT NULL,
	  expectation LONGTEXT     NOT NULL,
	  src_path    VARCHAR(512) NULL,
	  PRIMARY KEY (hs_id)
	)`,
	// NOTE: no FK on bc_id is possible — that is the whole point of the check.
	`CREATE TABLE IF NOT EXISTS hs_bc (
	  hs_id VARCHAR(16) NOT NULL,
	  bc_id VARCHAR(24) NOT NULL,
	  PRIMARY KEY (hs_id, bc_id),
	  CONSTRAINT fk_hsbc_hs FOREIGN KEY (hs_id) REFERENCES holdout_scenario (hs_id) ON DELETE CASCADE
	)`,
	`CREATE TABLE IF NOT EXISTS schema_migrations (
	  version    INT          NOT NULL,
	  name       VARCHAR(200) NOT NULL,
	  applied_at DATETIME     NOT NULL,
	  PRIMARY KEY (version)
	)`,
}

func ddlFor(zone string) []string {
	if zone == ZoneWalled {
		return walledDDL
	}
	return openDDL
}
