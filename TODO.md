# CodeQuest TODO

## Uncommitted v2.0 Work

- [ ] Commit v2.0 changes to git *(done — committed as of 2026-03-12)*
- [ ] Push to GitHub as public repo *(done — https://github.com/aiwitsam/codequest)*

## Known Gaps

### Testing
- [ ] Add test suite — no tests exist yet
- [ ] Unit tests for scanner.py (project detection, index caching)
- [ ] Unit tests for config.py (deep merge, path resolution)
- [ ] Unit tests for runner.py (run command detection by project type)
- [ ] Unit tests for scoring.py (heat badges, recommendation tiers)
- [ ] Integration tests for web routes (Flask test client)
- [ ] Verify all 68 routes return expected status codes

### Integrations (Defined but Not Wired)
- [ ] Linear integration — config has `linear_team` field, no implementation
- [ ] Jira integration — config has `jira_instance` and `jira_project`, no implementation
- [ ] Asana integration — config has `asana_workspace`, no implementation

### Intel Feed
- [ ] GitHub trending scraper — relies on HTML structure, may break on GitHub changes
- [ ] HuggingFace source — basic API call, could add filtering by task/library
- [ ] Queue persistence — YAML-based, no UI for viewing/managing queues
- [ ] Intel feed auto-refresh — currently manual page reload

### Ops Suite
- [ ] Mesh sync status — config has `mesh_host`, services.py reads it, but no deep mesh integration
- [ ] Security audit — read-only, no remediation actions or fix suggestions
- [ ] Service log viewing — services page shows status but no log tailing

### Web Dashboard
- [ ] Mobile responsiveness — retro CSS is desktop-focused
- [ ] Connection graph visualization — data API exists, frontend graph rendering could be richer
- [ ] Bulk operations — only bulk editor open exists, could extend to bulk git operations
- [ ] Notes — basic markdown notes per project, no search across notes

### TUI
- [ ] TUI doesn't have the v2.0 features (AI toolkit, intel, ops) — web only
- [ ] TUI project detail could show dependency/connection data

### General
- [ ] Add `LICENSE` file (MIT)
- [ ] Add `.github/` workflows (CI/CD)
- [ ] Package for PyPI distribution
- [ ] Add `--version` CLI flag
- [ ] Config validation — no schema validation on config load, bad YAML could crash

## Future Ideas

*Space for new feature ideas as they come up.*
