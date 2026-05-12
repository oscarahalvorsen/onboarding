# Onboarding

A Claude Code agent configuration that turns any repository into an onboarding-ready codebase. Point it at a repo and it produces orientation material like architecture summaries, component maps, reading orders, and Mermaid diagrams.

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

2. Copy both files to your Claude configuration directory:

   ```bash
   mkdir -p ~/.claude/hooks ~/.claude/agents
   cp repo_onboarding_guard.py ~/.claude/hooks/
   cp repo-onboarding.agent.md ~/.claude/agents/
   ```

   The agent file references the guard script at `$HOME/.claude/hooks/repo_onboarding_guard.py`, so the path resolves correctly for any user without editing.

   To limit the agent to a single project instead, copy `repo-onboarding.agent.md` into that project's `.claude/agents/` folder rather than `~/.claude/agents/`.

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

### Guard blocks all file operations with "git unavailable"

**Symptom:** Every tool call is denied with `git is unavailable or the working directory is not a git repository`.

**Fix:** Ensure `git` is on your `PATH` and that you are running Claude Code inside a git repository. The guard falls back to filename-pattern checks only and fails closed for file operations when git is unavailable.

---

### Agent edits code instead of producing documentation

**Symptom:** The agent attempts to write source files rather than markdown.

**Fix:** The guard will prompt for confirmation on broad code edits. If the agent drifts into implementation work, redirect it explicitly: `stay in documentation mode and do not edit source files`. The guard limits non-doc file writes to three files per session.
