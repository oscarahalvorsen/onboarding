---
name: repo-onboarding-docs
description: 'Create a consolidated repository onboarding document or structured summary. Use for onboarding guides, architecture summaries, tech stack overviews, major components, orchestration, reading order, and first-week orientation for new engineers.'
argument-hint: 'Repository path, audience, and desired output format'
user-invocable: true
---

# Repository Onboarding Docs

## When to Use
- Create or refresh a persistent onboarding document for a repository.
- Turn exploratory findings into a clean summary for new engineers.
- Produce a reading order that gets someone productive quickly.
- Capture the stack, architecture, and central concepts without drifting into low-value inventory work.

## Core Rules
- Start from decisive files and flows, not broad directory dumps.
- Optimize for orientation speed, not completeness.
- Separate facts, inferences, and open questions.
- Prefer one consolidated narrative over many disconnected sections.
- Only include commands or setup steps if they materially help onboarding.

## Procedure
1. Identify the repository purpose, composition roots, and runtime boundaries.
2. Extract the stack, deployment shape, and external dependencies.
3. Group the codebase into major subsystems and summarize each responsibility in one or two sentences.
4. Trace one to three critical flows that explain how the system behaves.
5. Fill the sections in the [onboarding template](./assets/onboarding-template.md).
6. Add a diagram only when it materially shortens the path to understanding.
7. End with a recommended reading order and any unresolved questions.

## Quality Bar
- A new engineer should know where to start reading after the first page.
- Every section should answer a concrete onboarding question.
- Prefer references to a few decisive files rather than many weak references.
- Call out missing documentation or naming that slows comprehension.