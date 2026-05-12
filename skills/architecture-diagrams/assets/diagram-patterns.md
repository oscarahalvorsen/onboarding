# Mermaid Diagram Patterns

## System Context

```mermaid
flowchart LR
    User[Engineer or Client]
    App[Primary Application]
    API[External API]
    Store[(Primary Data Store)]

    User --> App
    App --> API
    App --> Store
```

Use this when the onboarding question is: what does this repository talk to and where does it sit?

## Component Map

```mermaid
flowchart TB
    Entry[Entrypoint]
    Web[Web or API Layer]
    Domain[Domain Services]
    Infra[Infrastructure Adapters]
    Data[(Data Store)]

    Entry --> Web
    Web --> Domain
    Domain --> Infra
    Infra --> Data
```

Use this when the onboarding question is: how is the repository internally organized?

## Sequence Flow

```mermaid
sequenceDiagram
    actor User
    participant API
    participant Service
    participant Store

    User->>API: Request
    API->>Service: Validate and dispatch
    Service->>Store: Read or write
    Store-->>Service: Result
    Service-->>API: Response model
    API-->>User: Response
```

Use this when the onboarding question is: what happens in the important path?

## Diagram Caption Pattern
- What this diagram shows:
- The one boundary or handoff to notice first:
- What a new engineer should read next: