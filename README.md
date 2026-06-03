# AIDu AI Actor

`aidu.ai.actor` is the participant layer of the AIDu ecosystem.

An actor represents a participant in a workflow.

Examples include:

* AI Tutor
* AI Student
* Human Student
* Human Teacher

Actors receive tasks from a director, perform local reasoning, and return results.

Actors do not control workflow execution. Workflow control belongs to the director.

---

# Execution Model

```text
Director
    ↓
 Actor
    ↓
Controller
    ↓
Processors
    ↓
Artifacts
```

An actor encapsulates a local controller and exposes a simple interface to the outside world.

This separates:

* global workflow control,
* local reasoning,
* deployment and communication.

---

# Responsibilities

An actor:

* receives tasks,
* executes local reasoning,
* produces artifacts,
* updates workflow state,
* communicates with the director.

An actor does not:

* schedule other actors,
* execute workflows,
* control lesson flow.

---

# Architecture

```text
Workflow
    ↓
Director
    ↓
Actor
    ↓
Controller
    ↓
Processor
```

The actor serves as the boundary between workflow orchestration and local cognition.

---

# Example

```text
Director
    ↓
AI Tutor
    ↓
Math Tutor Processor
    ↓
Symbolic Solver Processor
    ↓
Response
    ↓
Director
```

The director sees only the actor.

Internal processors remain private implementation details.

---

# Communication

Actors may run locally or remotely.

Typical communication mechanisms include:

* REST
* Server-Sent Events (SSE)
* WebSockets

A director interacts with actors through messages and actor results.

```text
Task
    ↓
Actor
    ↓
Artifact + State Update
```

---

# Development

## Install Local Dependencies

```toml
[tool.uv.sources]
aidu-ai-controller = { path = "../aidu-ai-controller", editable = true }
aidu-support = { path = "../aidu-support", editable = true }
```

---

## Run Example

```bash
python -m examples.tutor_actor
```

---

## Run Smoke Tests

```bash
make smoke
```

Smoke tests verify:

* actor execution,
* controller integration,
* artifact propagation,
* actor/director interaction.

---

# Design Goals

The actor layer is intentionally lightweight.

Future versions may support:

* distributed deployment,
* actor discovery,
* actor registration,
* REST APIs,
* SSE event streams,
* workflow monitoring,
* remote execution.

---

# Relationship to Other Packages

```text
aidu-ai-core
    Shared data structures

aidu-ai-controller
    Local reasoning runtime

aidu-ai-actor
    Workflow participant

aidu-ai-director
    Workflow orchestration
```

Actors are the participants that perform work within workflows.

---

# License

MIT License.

Copyright (c) 2026 Wolfgang Spahn, PHBern.
