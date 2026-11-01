# Repository working rules

- Treat `docs/architecture.md` as the durable source of truth for current architecture.
  Check it and relevant topic docs against the implementation before making changes.
- Update current documentation when behavior, architecture, security or operations
  permanently change. Document the resulting system, not the implementation chronology.
- Keep phase/task reports, rollout approvals, checkpoints and internal investigations
  under ignored `work/phases/`. Keep generated logs, screenshots and execution
  measurements under ignored `work/evidence/` unless a specific reviewed design asset
  is intentionally selected for version control.
- Public commits should contain intended code, tests and durable current documentation.
  Never automatically stage every generated Markdown file or use a broad add operation
  that includes unrelated working-tree files. Review the explicit file list first.
- Do not publish credentials, connection strings, private account/learner identifiers,
  personal addresses, capability material, transcripts or private reference sources.
- Preserve unrelated edits and local journals. Moving a report requires verifying its
  complete ignored local copy before removing the repository copy.
- Documentation work does not authorize production configuration changes, database
  operations, account changes, feature activation or learner linking.
- Keep normal local development on loopback and use disposable databases for tests.
  Run focused checks appropriate to the change; do not send real AI/audio/email traffic
  or access production data merely to verify documentation.
