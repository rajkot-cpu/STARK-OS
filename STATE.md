# STATE — read first, updated last
Last updated: 2026-10-28 ~02:30 (Asia/Calcutta)

## Goals
- Build STARK OS on the Grok Bot box, test it, then package an install for Dr Chandan kumar's computer.
- Day-1 MVP and Day 2–3 read-only skills are complete on this host.

## Status
- Windows-native day-to-day scripts live: scripts/win/*.py + Start-Jarvis.ps1 on chandan (workday_start verified 2026-10-28).
- User-computer install: Windows `chandan` has C:/Users/rajk1/jarvis (2026-10-28). INSTALL_USER OK. git/bash missing on that PC — shell skills need Git Bash/WSL; day-to-day brief stays on this Grok Bot host.
- Day-to-day loop ready on box: `./scripts/workday_start.sh`; 07:30 routine prompt refreshed for calendar+mail cache.
- Polish pass 2026-10-28 (branch jarvis/chore/polish-pass): quiet hours 22:00-07:00 IST + in_quiet_hours.sh; pre-commit hook (precommit_smoke.sh ~1.5s); evals 03/05/06/07 runnable & PASS; KAREN karen_smoke.sh + health-audit skill; EDITH secret scan; session_start shows branch/POLICY/quiet/backup; Chrome first-run note.
- Live app launch (Chrome + xfce4-terminal) verified on box desktop 2026-10-28; backup script + first tarball restore-tested.
- Day 1: complete (exit tests PASS). POLICY.yaml and host/permission-rules.md approved 2026-10-28 by Dr Chandan kumar.
- Day 2–3: complete (16/16 exit tests PASS). Merged `jarvis/feat/day2-readonly-skills` into `main` at `60112fa` (user OK t2s7).
- Draft-only Daily Brief routine saved: every day around 07:30 Asia/Calcutta → writes `reports/YYYY-MM-DD.md` and posts a short receipt in this chat; skips quietly if today's report already exists.
- Box install hardened (branch jarvis/feat/box-install-harden, ff-merged to main): install_box.sh OK; session_start.sh; kill_switch.md; Day 4–5 app-control (allowlist chrome=google-chrome, terminal=xfce4-terminal) 13/13 PASS; golden evals day1/day2/day4 all PASS via run_golden_evals.sh.
- Install on user computer: done (Windows mirror); ops still orchestrated from box.
- Desktop `chandan` still disconnected; OnePlus connected; Docker unavailable.

## Status addendum (day-to-day ops)
- workday-start skill, enriched brief (calendar+Gmail read-only cache), day_to_day_checklist, eval_06b live.
- ROUTINE PROMPT NEEDS PARENT REFRESH: apply scripts/routine-prompts/daily-brief-0730.md via UpdateRoutine.

## Status addendum (windows-room)
- 2026-11-04: `apps/windows-room` added. pywebview host imports `apps/windows-cc` `BridgeApi` (not a second bridge). Three.js workshop UI, `build_exe.ps1` writes `JarvisRoom.exe` only. `Jarvis.exe` and `Jarvis3D.exe` build scripts unchanged. The dated workshop plan/spec files were not on `main` or `origin/jarvis/feat/command-center`.

## Next steps
1. Let morning brief run (or run `skills/daily-brief-draft/scripts/brief.sh --write-report` for a manual dry run).
2. Optionally fill intake (OS, daily apps, top three tasks) and real restricted-folder paths in POLICY.
3. Day 4–5 + polish done on box. Next: package install for user computer (needs desktop `chandan` connected).

## Decisions owed
- Real paths for restricted folders (patient / banking / tax placeholders remain).
- Optional intake answers (skipped earlier).
- When to start packaging install for the user's computer / connect desktop `chandan`.

## Host capabilities
- Files + shell on box (Debian 13): verified
- Git + gh; GitHub connector: verified
- Browser + network: verified
- Live connectors: Gmail, Calendar, Notion, Docs/Slides, X, TubeAlfred, MagicPath, Clay, Wonder, Origin
- Needs auth: Composio, Read.ai, GitLab, Finance
- OnePlus 13: connected; desktop `chandan`: disconnected; Docker: unavailable
- OS backups on user machines: unknown
