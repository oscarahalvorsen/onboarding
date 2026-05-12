import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path


DOC_EXTENSIONS = {
    ".md",
    ".mdx",
    ".txt",
    ".rst",
    ".adoc",
    ".mermaid",
    ".mmd",
}

CUSTOMIZATION_MARKERS = (
    "/.github/agents/",
    "/.github/skills/",
    "/.copilot/skills/",
    "/Code/User/prompts/",
    # /.github/hooks/ and /.copilot/hooks/ are intentionally excluded:
    # hook scripts are the enforcement layer itself and must never be
    # silently writable by the agent they guard.
)

MUTATING_COMMAND_PATTERNS = (
    r"\bnpm\s+(install|add|update)\b",
    r"\bpnpm\s+(add|install|update)\b",
    r"\byarn\s+(add|install|up|upgrade)\b",
    r"\bpip\s+install\b",
    r"\bpoetry\s+add\b",
    r"\bcargo\s+(add|build|run|test)\b",
    r"\bgo\s+(get|build|test)\b",
    r"\bgit\s+(commit|push|merge|rebase|checkout|switch|reset)\b",
    r"\brm\s+-",
    r"\bmv\b",
    r"\bcp\b",
    r"\bsed\s+-i\b",
)

# Commands that decode or execute obfuscated content.  An onboarding agent has
# no legitimate need for any of these; their presence is a reliable signal that
# something is trying to bypass the filename-based checks above.
OBFUSCATION_PATTERNS = (
    r"\bbase64\b.{0,60}(?:-d|--decode)\b",  # base64 -d / base64 --decode
    r"\bbase64\b.*\|\s*(?:bash|sh|zsh)\b",  # base64 ... | bash  (exec decoded)
    r"\bopenssl\s+enc\b.*-d\b",             # openssl enc -d  (symmetric decrypt)
    r"\bxxd\s+-r\b",                         # xxd -r  (hex decode)
    r"\beval\s+.*\$\(",                      # eval $(...)  (eval of subshell output)
)

# Ignore files that follow gitignore pattern syntax, checked in addition to git.
# Ordered from most specific (AI tools) to most general.
SUPPLEMENTAL_IGNORE_FILES = (
    ".claudeignore",    # Claude Code
    ".cursorignore",    # Cursor
    ".copilotignore",   # GitHub Copilot
    ".aiderignore",     # Aider
    ".aiexclude",       # generic AI-tool exclusion
    ".codeiumignore",   # Codeium
    ".dockerignore",    # Docker (widely used for secret exclusion)
    ".npmignore",       # npm
    ".gitignore",       # manual fallback when git is unavailable
)

# Defense-in-depth: deny reads of these filenames even if they are not gitignored.
# An onboarding agent has no legitimate reason to read these files.
# This catches secrets that were accidentally omitted from .gitignore.
_HIGH_RISK_RE = re.compile(
    r"(?:^|[/\\])("
    r"\.env(\.[^/\\]*)?"        # .env, .env.local, .env.production, …
    r"|\.netrc"                  # network credentials (curl, ftp, etc.)
    r"|\.htpasswd"               # HTTP basic-auth password files
    r"|.*\.pem"                  # TLS certificates / private keys
    r"|.*\.p12"                  # PKCS#12 bundles
    r"|.*\.pfx"                  # PFX bundles (same as p12)
    r"|.*\.jks"                  # Java KeyStore
    r"|id_rsa(\.pub)?"           # RSA SSH key pair
    r"|id_ed25519(\.pub)?"       # Ed25519 SSH key pair
    r"|id_ecdsa(\.pub)?"         # ECDSA SSH key pair
    r"|id_dsa(\.pub)?"           # DSA SSH key pair (legacy)
    r")$",
    re.IGNORECASE,
)

# Tool names used for reading file contents across common agent frameworks.
READ_TOOL_NAMES = frozenset({
    "read_file",
    "get_file_contents",
    "view_file",
    "open_file",
    "read",
    "show_file",
})

# Field names that carry the target path in read tool inputs.
READ_PATH_FIELDS = ("filePath", "path", "file_path", "filename", "file", "target")

# Splits a shell command on whitespace and shell metacharacters, including
# parentheses.  Using parentheses as delimiters lets us extract filenames
# embedded inside function calls: open('.env'), readFileSync('id_rsa'), etc.
_SHELL_DELIMITERS = re.compile(r'[\s|&;`()]+')
_QUOTE_STRIP = "\"'\\"

_repo_root: Path | None = None


def _find_repo_root() -> Path:
    global _repo_root
    if _repo_root is not None:
        return _repo_root
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            _repo_root = Path(result.stdout.strip())
            return _repo_root
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    _repo_root = Path.cwd()
    return _repo_root


def _git_ignores(path_str: str, repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", "--", path_str],
            cwd=repo_root,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def _gitignore_pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """
    Convert a single gitignore pattern to a compiled regex.

    Handles the gitignore-specific glob extensions that fnmatch does not:
      **   matches any sequence of characters including path separators
      *    matches any sequence of characters except /
      ?    matches any single character except /

    Negation (!) and directory-trailing (/) are handled by the caller.
    """
    tokens = re.split(r"(\*\*|\*|\?)", pattern)
    parts: list[str] = []
    for token in tokens:
        if token == "**":
            parts.append(".*")
        elif token == "*":
            parts.append("[^/]*")
        elif token == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(token))
    return re.compile("^" + "".join(parts) + "$")


def _match_gitignore_pattern(rel_path: str, pattern: str) -> bool:
    """Match one gitignore-style pattern against a repo-relative path."""
    pattern = pattern.rstrip()
    if not pattern or pattern.startswith("#") or pattern.startswith("!"):
        return False

    dir_only = pattern.endswith("/")
    if dir_only:
        pattern = pattern[:-1]

    if pattern.startswith("/"):
        # Rooted: anchored to repo root — match full path or any path beneath.
        rooted = pattern[1:]
        rx = _gitignore_pattern_to_regex(rooted)
        return bool(rx.match(rel_path)) or bool(
            _gitignore_pattern_to_regex(rooted + "/*").match(rel_path)
        )

    if "/" in pattern:
        # Pattern with interior slash: relative to repo root.
        rx = _gitignore_pattern_to_regex(pattern)
        return bool(rx.match(rel_path)) or bool(
            _gitignore_pattern_to_regex(pattern + "/*").match(rel_path)
        )

    # Plain filename pattern: match against any single path component.
    rx = _gitignore_pattern_to_regex(pattern)
    return any(bool(rx.match(part)) for part in Path(rel_path).parts)


def _supplemental_ignores(path_str: str, repo_root: Path) -> tuple[bool, str | None]:
    """Check non-git ignore files. Returns (ignored, source_filename)."""
    try:
        abs_path = Path(path_str)
        if not abs_path.is_absolute():
            abs_path = (repo_root / abs_path).resolve()
        rel_path = str(abs_path.relative_to(repo_root))
    except (ValueError, OSError):
        rel_path = path_str.replace("\\", "/").lstrip("/")

    for name in SUPPLEMENTAL_IGNORE_FILES:
        ignore_file = repo_root / name
        if not ignore_file.is_file():
            continue
        try:
            lines = ignore_file.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if _match_gitignore_pattern(rel_path, line.strip()):
                return True, name

    return False, None


def _is_high_risk(path_str: str) -> bool:
    """Return True if the filename matches a well-known secret-file pattern."""
    normalized = path_str.replace("\\", "/")
    return bool(_HIGH_RISK_RE.search(normalized))


def _resolve_symlink_target(path_str: str, repo_root: Path) -> str | None:
    """
    Return the fully-resolved real path if the given path is a symlink, else None.
    Uses strict=False so missing path components do not raise.
    """
    try:
        abs_path = Path(path_str)
        if not abs_path.is_absolute():
            abs_path = repo_root / abs_path
        resolved = abs_path.resolve(strict=False)
        if resolved != abs_path:
            return str(resolved)
    except (OSError, ValueError):
        pass
    return None


def is_ignored(path_str: str) -> tuple[bool, str | None]:
    """
    Return (ignored, reason).

    Checks in order:
      1. git check-ignore  (authoritative; handles nested .gitignore, global ignore, etc.)
      2. Supplemental ignore files  (.claudeignore, .dockerignore, etc.)
      3. Hardcoded high-risk filename patterns  (defense-in-depth for files
         that contain secrets but were accidentally omitted from .gitignore)

    Each check is repeated against the symlink target if the path is a symlink,
    so that `config.local -> .env` is caught even though `config.local` itself
    is not listed in any ignore file.
    """
    repo_root = _find_repo_root()

    for candidate, suffix in _candidates(path_str, repo_root):
        if _git_ignores(candidate, repo_root):
            return True, ".gitignore" + suffix

        supp, source = _supplemental_ignores(candidate, repo_root)
        if supp:
            return True, source + suffix

        if _is_high_risk(candidate):
            return True, "high-risk filename pattern" + suffix

    return False, None


def _candidates(path_str: str, repo_root: Path):
    """Yield (path, label_suffix) for the path itself, then its symlink target if any."""
    yield path_str, ""
    target = _resolve_symlink_target(path_str, repo_root)
    if target:
        yield target, " (symlink target)"


def _normalize_path_str(value: str) -> str:
    """Strip file:// prefix and normalise separators."""
    text = value.replace("\\", "/")
    if text.startswith("file://"):
        text = text[7:]
    return text


def _extract_read_path(tool_name: str, tool_input: dict) -> str | None:
    if tool_name not in READ_TOOL_NAMES:
        return None
    for field in READ_PATH_FIELDS:
        val = tool_input.get(field)
        if isinstance(val, str) and val.strip():
            return _normalize_path_str(val.strip())
    return None


def _potential_paths_in_command(command: str) -> list[str]:
    """
    Extract candidate file paths from a shell command string.

    Two extraction passes per raw token:
      1. The whole token (after quote-stripping) — catches normal arguments.
      2. The right-hand side of the first `=` in the token — catches assignment
         forms such as `x='.env'` and `--config=secrets.yml`.

    Splits on shell metacharacters including parentheses so that filenames
    inside function calls are also extracted:
      grep "pw" .env                          → .env
      python3 -c "open('.env').read()"        → .env   (parens split open())
      python3 -c "x='.env'; open(x).read()"  → .env   (= split on assignment)
      node -e "fs.readFileSync('id_rsa')"     → id_rsa
      cat $HOME/.ssh/id_rsa                   → $HOME/.ssh/id_rsa (→ id_rsa matched)

    Remaining gap: paths constructed at runtime — os.path.join(d, name),
    string concatenation, environment-variable expansion of the full path
    ($SECRET_FILE) — are undetectable statically.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in _SHELL_DELIMITERS.split(command):
        # Yield the token itself, then (if it contains `=`) its RHS.
        sub_tokens = [raw]
        if "=" in raw:
            sub_tokens.append(raw.split("=", 1)[1])

        for sub in sub_tokens:
            candidate = _normalize_path_str(sub.strip(_QUOTE_STRIP))
            if (
                candidate
                and candidate not in seen
                and not candidate.startswith("-")   # skip flags
                and "://" not in candidate          # skip URLs
                # Note: $VAR is NOT skipped — $HOME/.ssh/id_rsa still
                # exposes `id_rsa` as the basename for high-risk matching.
            ):
                seen.add(candidate)
                result.append(candidate)
    return result


def _check_terminal_for_ignored_reads(command: str) -> tuple[str, str] | None:
    """
    Block terminal commands that reference gitignored or high-risk files.

    Checks every candidate token — not just arguments to a fixed list of
    read commands — so grep, awk, vim, diff, python/node one-liners, and
    find -exec are all covered by the same logic.
    """
    for candidate in _potential_paths_in_command(command):
        ignored, source = is_ignored(candidate)
        if ignored:
            return (
                "deny",
                f"Terminal command references '{candidate}' which is excluded by {source}. "
                "This file may contain secrets or credentials.",
            )
    return None


def emit(decision, reason, additional_context=None):
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }

    if additional_context:
        payload["hookSpecificOutput"]["additionalContext"] = additional_context

    json.dump(payload, sys.stdout)


def normalize_path(value):
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.replace("\\", "/")
    if text.startswith("file://"):
        text = text[7:]
    return text


def is_doc_or_customization(path_text):
    normalized = normalize_path(path_text)
    if not normalized:
        return False

    if any(marker in normalized for marker in CUSTOMIZATION_MARKERS):
        return True

    return Path(normalized).suffix.lower() in DOC_EXTENSIONS


def extract_paths(tool_name, tool_input):
    if tool_name == "create_file":
        return [tool_input.get("filePath")]

    if tool_name == "create_directory":
        return [tool_input.get("dirPath")]

    if tool_name == "apply_patch":
        patch_text = tool_input.get("input", "")
        return re.findall(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)(?: -> .+)?$", patch_text, re.MULTILINE)

    return []


def should_block_paths(paths):
    normalized = [path for path in (normalize_path(item) for item in paths) if path]
    if not normalized:
        return None

    # Hard-deny writes to any gitignored or high-risk file.
    for path in normalized:
        ignored, source = is_ignored(path)
        if ignored:
            return (
                "deny",
                f"Writing to '{path}' is blocked: it is excluded by {source}. "
                "This file may contain secrets or credentials.",
            )

    non_doc_paths = [path for path in normalized if not is_doc_or_customization(path)]
    if not non_doc_paths:
        return None

    if len(non_doc_paths) > 3 or len(normalized) > 5:
        return (
            "deny",
            "Repository Onboarding is in documentation mode. Broad edits across code files are blocked.",
        )

    return (
        "ask",
        "Repository Onboarding is intended for analysis and documentation. Confirm before editing code or runtime files.",
    )


def should_block_command(command):
    if not isinstance(command, str):
        return None

    stripped = command.strip()
    if not stripped:
        return None

    for pattern in MUTATING_COMMAND_PATTERNS:
        if re.search(pattern, stripped):
            return (
                "ask",
                "Repository Onboarding may use the terminal for evidence gathering, but mutating commands require confirmation.",
            )

    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        emit("allow", "Invalid hook input could not be parsed.")
        return

    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    # Block reads of gitignored / AI-excluded / high-risk files.
    read_path = _extract_read_path(tool_name, tool_input)
    if read_path:
        ignored, source = is_ignored(read_path)
        if ignored:
            emit(
                "deny",
                f"Reading '{read_path}' is blocked: excluded by {source}. This file may contain secrets.",
                "Repository Onboarding does not read gitignored or AI-excluded files to protect secrets and credentials.",
            )
            return

    if tool_name in {"apply_patch", "create_file", "create_directory"}:
        decision = should_block_paths(extract_paths(tool_name, tool_input))
        if decision:
            emit(
                decision[0],
                decision[1],
                "Prefer docs, onboarding assets, diagrams, and customization files unless the user explicitly asks for implementation work.",
            )
            return

    if tool_name == "run_in_terminal":
        command = tool_input.get("command", "")

        for pattern in OBFUSCATION_PATTERNS:
            if re.search(pattern, command):
                emit(
                    "deny",
                    "Terminal command uses obfuscation (base64 decode, hex decode, eval, etc.). "
                    "Repository Onboarding never needs to decode or execute obfuscated commands.",
                    "This is a strong signal that something is attempting to bypass filename-based secret detection.",
                )
                return

        terminal_read_block = _check_terminal_for_ignored_reads(command)
        if terminal_read_block:
            emit(
                terminal_read_block[0],
                terminal_read_block[1],
                "Repository Onboarding does not read gitignored or AI-excluded files to protect secrets and credentials.",
            )
            return

        decision = should_block_command(command)
        if decision:
            emit(
                decision[0],
                decision[1],
                "Use read-only commands for repository understanding unless the user explicitly wants operational or implementation changes.",
            )
            return

    emit("allow", "Allowed by Repository Onboarding guard.")


if __name__ == "__main__":
    main()
