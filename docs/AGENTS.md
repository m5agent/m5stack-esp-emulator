# Documentation maintenance

The [root guidance](../AGENTS.md) applies. Read [the documentation index](README.md)
before changing a claim. The default project homepage is Chinese `README.md`;
`README.en.md` is its English counterpart. Keep their capabilities, commands,
links and limitations aligned without copying the full engineering ledger.

## Keep each document's role

- `project-status.md`: current capability and risk, with links to evidence.
- `project-backlog.md`: only unfinished work, dependencies and acceptance; it
  is the sole queue, not another history/PASS table.
- `validation-ledger.md`: dated observations and exact evidence identities.
- `runtime-model-gap-register.md`: concrete runtime gaps and closure conditions.
- `code-map.md`: actual module/tool and validation entry points.
- `project-snapshot.md`: generated inventory; use
  `python3 platform/tools/project_snapshot.py --write`, then `--check`.

Do not promote an old topic page or case README into a current authority.
Correct stale current claims from source/registries and actual evidence; retain
dated failures and their original hashes as history. A source/build/HTTP check
must not become a browser guest, native guest, all-device or hardware PASS.

## Review a documentation change

- Give newcomers the shortest useful introduction, runnable path and scope
  boundary. Link detailed API/build/validation material rather than copying it
  into both homepages. Avoid machine-specific service facts and temporary
  worktree/cache paths in public setup instructions.
- Link new pages from `docs/README.md` with the appropriate role and review
  date. An area README describes its local workflow; do not maintain a second
  mutable device or test count there.
- Small curated screenshots, model galleries and diagrams may be committed
  under `docs/images/` as documentation illustrations. Record source/run or
  model identity, intended use and visual review, and preserve applicable
  licenses. Label model-only or no-firmware scenes accordingly; an illustration
  does not imply runtime or hardware validation. Keep raw execution logs,
  uncurated screenshots and full frame series in ignored artifact storage.
- Validate relative links, image paths, JSON, UTF-8 and command entry points.
  Render/open the homepages and images. Do not start guests or restart services
  merely to validate prose; screenshot collection follows the root test route.
- Run affected `platform/tests/test_docs*_contract.py` checks. When adding a
  module or API, its source/API tests remain necessary. Do not weaken a contract
  just to fit obsolete wording; revise it only when the documented requirement
  actually changed.
- Generate the project snapshot after all source and Markdown edits finish,
  then run checks sequentially. Do not run a snapshot-count assertion while
  its generator is still writing the file.

Keep externally published summaries within the root evidence/privacy budget.
Document known limitations plainly; neither an omitted test nor a later passing
subcase closes an entire workstream.
