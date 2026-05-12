# twoday/onboarding

A Claude Code agent configuration that turns any repository into an onboarding-ready codebase. Point it at a repo and it produces orientation material — architecture summaries, component maps, reading orders, and Mermaid diagrams — optimised for new engineers.

---

## Installation

**Prerequisites**

- [Claude Code](https://claude.ai/code) installed and authenticated
- Python 3.9+ (for the security guard hook)
- Git

**Steps**

1. Clone the repository:

   ```bash
   git clone <repo-url>
   cd onboarding
   ```

2. Register the agent in Claude Code by copying the agent file to your Claude configuration directory, or open the repo directly in Claude Code — the `.claude/` directory is picked up automatically.

3. Update the hook path in `repo-onboarding.agent.md` to point to your local copy of the guard script:

   ```yaml
   hooks:
     PreToolUse:
       - type: command
         command: "/usr/bin/env python3 '/your/local/path/repo_onboarding_guard.py'"
         timeout: 10
   ```

---

## Configuration

The agent has no environment variables. All configuration lives in two files.

| File | Purpose |
|---|---|
| `repo-onboarding.agent.md` | Agent definition: tools, skills, hooks, and behavioral instructions |
| `repo_onboarding_guard.py` | PreToolUse hook that enforces read-only, secret-safe access |

### Guard customisation

The guard (`repo_onboarding_guard.py`) controls what the agent is allowed to do. You can adjust these constants near the top of the file:

- `MUTATING_COMMAND_PATTERNS` — shell patterns that trigger a confirmation prompt before running
- `SUPPLEMENTAL_IGNORE_FILES` — additional ignore-file names checked alongside `.gitignore`
- `_HOME_RELATIVE_DENYLIST` — home-directory paths that are always blocked (`.aws/`, `.ssh/`, etc.)

No restart is required; the hook is re-executed from disk on every tool call.

---

## Usage

### Explore an unfamiliar repository

Open a repository in Claude Code, then invoke the agent:

```
@Repository Onboarding give me an overview of this codebase
```

The agent identifies the composition roots, extracts the tech stack and runtime boundaries, maps the major components, and traces one to three critical code flows. It returns a consolidated onboarding summary directly in chat.

Expected output: a structured narrative covering repository purpose, stack, major subsystems, key flows, and a recommended reading order.

### Produce a persistent onboarding document

```
@Repository Onboarding create an onboarding doc for the payments service
```

The agent invokes the `repo-onboarding-docs` companion skill, fills the structured template, and writes a markdown document to the repository. Use the optional argument to scope the output to a specific area or audience.

Expected output: a saved `.md` file with sections for purpose, architecture, key flows, core concepts, reading order, and open questions.

### Generate an architecture diagram

```
@Repository Onboarding draw a component map for the auth subsystem
```

The agent invokes the `architecture-diagrams` skill and produces a Mermaid diagram grounded in actual code paths. Diagrams are added only when they materially reduce ambiguity.

Expected output: a Mermaid diagram block with a short caption, inline in chat or embedded in the onboarding document.

---

## Common Issues

### Hook path not found

**Symptom:** `PreToolUse hook failed: No such file or directory`

**Fix:** Update the `command` path in `repo-onboarding.agent.md` to the absolute path where you cloned the guard script.

---

### Guard blocks all file operations with "git unavailable"

**Symptom:** Every tool call is denied with `git is unavailable or the working directory is not a git repository`.

**Fix:** Ensure `git` is on your `PATH` and that you are running Claude Code inside a git repository. The guard falls back to filename-pattern checks only and fails closed for file operations when git is unavailable.

---

### Agent edits code instead of producing documentation

**Symptom:** The agent attempts to write source files rather than markdown.

**Fix:** The guard will prompt for confirmation on broad code edits. If the agent drifts into implementation work, redirect it explicitly: `stay in documentation mode and do not edit source files`. The guard limits non-doc file writes to three files per session.
