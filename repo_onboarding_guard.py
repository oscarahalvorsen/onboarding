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
    "/.github/hooks/",
    "/.copilot/skills/",
    "/.copilot/hooks/",
    "/Code/User/prompts/",
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

# Regex that extracts the first non-flag argument from cat-like terminal commands.
# Best-effort: handles the most common cases, not all shell quoting variants.
_READ_CMD_RE = re.compile(
    r'\b(?:cat|less|more|head|tail|bat|type|print)\s+(?:-\S+\s+)*([^\s|&;<>]+)',
    re.IGNORECASE,
)

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


def _match_gitignore_pattern(rel_path: str, pattern: str) -> bool:
    """Match one gitignore-style pattern against a repo-relative path."""
    pattern = pattern.rstrip()
    if not pattern or pattern.startswith("#") or pattern.startswith("!"):
        return False

    if pattern.endswith("/"):
        pattern = pattern[:-1]

    if pattern.startswith("/"):
        # Rooted pattern: anchored to repo root.
        pattern = pattern[1:]
        return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, f"{pattern}/*")

    if "/" in pattern:
        # Pattern with interior slash: relative to root.
        return fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(rel_path, f"{pattern}/*")

    # Plain filename pattern: match any path component.
    return any(fnmatch.fnmatch(part, pattern) for part in Path(rel_path).parts)


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


def is_ignored(path_str: str) -> tuple[bool, str | None]:
    """Return (ignored, reason) using git then supplemental ignore files."""
    repo_root = _find_repo_root()

    if _git_ignores(path_str, repo_root):
        return True, ".gitignore"

    supp, source = _supplemental_ignores(path_str, repo_root)
    if supp:
        return True, source

    return False, None


def _extract_read_path(tool_name: str, tool_input: dict) -> str | None:
    if tool_name not in READ_TOOL_NAMES:
        return None
    for field in READ_PATH_FIELDS:
        val = tool_input.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _check_terminal_for_ignored_reads(command: str) -> tuple[str, str] | None:
    """Block cat/less/etc. on ignored files. Returns (decision, reason) or None."""
    for match in _READ_CMD_RE.finditer(command):
        path = match.group(1).strip("\"'")
        ignored, source = is_ignored(path)
        if ignored:
            return (
                "deny",
                f"Reading '{path}' via terminal is blocked: it is excluded by {source}. "
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

    # Block reads of gitignored / AI-excluded files (secrets protection).
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
