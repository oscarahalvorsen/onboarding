---
name: architecture-diagrams
description: 'Create concise Mermaid diagrams for repository onboarding. Use for architecture maps, component relationships, request flows, event flows, sequence diagrams, and visual summaries that help new engineers understand a codebase faster.'
argument-hint: 'System or flow to visualize and desired diagram type'
user-invocable: true
---

# Architecture Diagrams

## When to Use
- A visual summary will reduce ambiguity faster than prose.
- You need to explain boundaries, ownership, or orchestration.
- You need a request, job, or event flow for onboarding.
- A component map would help a new engineer place files and responsibilities.

## Diagram Rules
- Only draw a diagram to answer a concrete onboarding question.
- Keep diagrams small enough to scan quickly.
- Match names and boundaries used in the repository.
- Prefer one strong diagram over several weak ones.
- If a diagram cannot be grounded in evidence, do not draw it.

## Procedure
1. Choose the smallest diagram type that answers the question.
2. Extract actors, components, or steps from decisive code paths.
3. Draft the diagram using one of the [diagram patterns](./assets/diagram-patterns.md).
4. Keep labels short and align them with repository terminology.
5. Add a short caption that explains what the reader should notice first.

## Preferred Diagram Types
- System context: for major services, stores, and external dependencies.
- Component map: for modules and ownership boundaries inside one repository.
- Sequence diagram: for request, job, or event flows.

## Review Checklist
- The diagram answers one clear question.
- The diagram is consistent with the code.
- The diagram omits low-value implementation detail.
- The caption highlights the eureka moment.