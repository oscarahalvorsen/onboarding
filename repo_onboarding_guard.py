import json
import re
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
        decision = should_block_command(tool_input.get("command"))
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