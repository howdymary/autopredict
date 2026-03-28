# Archive

This folder is intentionally minimal.

The repo used to carry a large set of historical phase summaries, calibration deep-dives, prompt
artifacts, and internal evaluation notes. Those files were removed from the working tree to keep the
public repository smaller and easier to scan.

What to use instead:

- [../../README.md](../../README.md): current project entrypoint
- [../../QUICKSTART.md](../../QUICKSTART.md): current onboarding path
- [../README.md](../README.md): current docs index
- `git log -- docs/archive` and `git show <commit>:<path>`: recover older archival material when needed

Rule of thumb:

- active usage guidance belongs under `docs/`
- runtime code belongs under `autopredict/`
- historical analysis should live in git history rather than the default checkout unless it is still
  operationally useful
