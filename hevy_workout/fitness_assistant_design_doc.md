# Fitness Coach Agentic System — High-Level Design (Slack-Threaded)

## Purpose

Design an opinionated, push-oriented personal training system that:

* Maintains a long-term model of the athlete
* Sets clear training intent **before** workouts
* Applies intelligent pressure (not hype)
* Evolves slowly and defensibly over time
* Operates naturally inside **Slack threads** as the primary UI

This document defines **layers, responsibilities, tools, agent boundaries, Slack integration, agent framework, and backend data ownership**. It is high-level and implementation-agnostic.

---

## Core Design Principles

1. **Intent before analysis** — decisions happen before workouts, not after
2. **Slow beliefs, fast execution** — training thesis updates slowly; session logic adapts quickly
3. **Opinionated but overrideable** — the system pushes; the user can consciously override
4. **Controlled novelty** — new exercises are rare, justified, and optional
5. **Minimal but meaningful data** — trends and constraints matter more than raw logs
6. **Threads = sessions** — Slack thread context defines workout scope
7. **Tool-driven reasoning** — agents use tools via function-calling framework (LangChain)

---

## Slack Interaction Model

Slack is the primary interface.

* **Each Slack thread corresponds to one workout session**
* The first message in a thread is a **cold start**
* All replies in the same thread share full conversational context
* No session plans are persisted — the thread *is* the session state

### Session Phases (Phase detection via prompt + context)

1. **Planning Phase (thread start)**

   * Agent calls tools to gather trends, weekly goals, exercise frequency
   * Proposes session options

2. **Execution Phase (mid-thread)**

   * Agent reacts to logged sets, notes, and pivots
   * No re-planning unless explicitly requested

3. **Guardrail Phase (reactive)**

   * Caps intensity
   * Preserves volume
   * Suggests substitutions for pain or equipment issues

---

## System Layers & Cadence

| Layer                 | Cadence    | Primary Role                            |
| --------------------- | ---------- | --------------------------------------- |
| Coach Doc             | Biweekly   | Training thesis & long-term direction   |
| Weekly Goals Doc      | Weekly     | Pressure, ambition, and focus           |
| Workout Session Agent | Per thread | Planning + live coaching (Slack-native) |

---

## Layer 1: Coach Doc (Biweekly)

### Purpose

Authoritative model of the athlete.

### Owns

* Strengths vs weaknesses (relative, trend-based)
* Movement pattern gaps
* Long-term priorities
* Training hypotheses
* Constraints (fatigue tolerance, injury risk, schedule realities)

### Does NOT Do

* Set daily workouts
* Set weekly PR targets
* React to single workouts or short-term noise
* Introduce new exercises directly

### Update Rules

* Default: every 2 weeks
* Forced update only for stagnation, pain, or explicit user challenge

### User Interaction

* Short summary delivered
* Limited feedback allowed

---

## Layer 2: Weekly Goals Doc (Weekly)

### Purpose

Translates Coach Doc into **measurable, uncomfortable ambition**.

### Owns

* Weekly theme
* PRs, volume targets, exposure counts
* Non-negotiables
* Flex zones
* Optional 0–3 new exercise proposals

### Must Include

* ≥1 uncomfortable constraint
* ≥1 measurable pass/fail condition

### Does NOT Do

* Fully prescribe workouts
* Change the long-term thesis
* Add ambition mid-week (can only reduce/swap)

---

## Layer 3: Workout Session Agent (Daily Planner + Live Coach)

### Purpose

Single agent per Slack thread that:

* Plans session at thread start
* Coaches live execution
* Enforces guardrails

### Behavior

* **Planning Phase**: calls tools to generate 2–3 session options
* **Execution Phase**: responds to logged sets, notes, and pivots
* **Guardrail Phase**: caps intensity, preserves volume, substitutes exercises

### Does NOT Do

* Change weekly goals
* Analyze long-term trends
* Introduce new exercises independently

### Implementation

* **Framework:** Python + **LangChain**
* Each tool is a LangChain `Tool` with structured input/output
* Agent receives **Slack thread context** + tool definitions
* Phase detection handled via prompt + conversation history

---

## Exercise Intelligence Model

1. **Exercise Repertoire**: known exercises, metadata, usage, and trend
2. **Equipment Profile**: gym equipment constraints
3. **Controlled Novelty**: new exercises only via Weekly Goals Doc, 0–3/week, justified, evaluated

---

## Tools

| Tool                     | Input                   | Output                 |
| ------------------------ | ----------------------- | ---------------------- |
| `get_workout_history`    | timeframe               | workouts + notes       |
| `get_exercise_trend`     | exercise ID + timeframe | trend summary + notes  |
| `get_exercise_frequency` | timeframe               | exercises hit + counts |
| `fetch_coach_doc`        | -                       | latest coach doc       |
| `fetch_weekly_goals`     | n                       | last n weekly goals    |

Tools implemented as Python functions + wrapped in LangChain `Tool` objects.

---

## Agent Responsibilities & Tool Access

* **Coach Doc Agent**: 2, 3, 4; biweekly
* **Weekly Goals Agent**: 2, 3, 5; weekly
* **Workout Session Agent**: per-thread; start → 3,5; mid-thread → 1
* **Drift/Critic Agent**: 2,5; triggers Coach Doc review

---

## Backend & Data Ownership

* **Hevy**: source of truth
* **S3**: versioned Coach Docs, Weekly Goals Docs, optional workout backups
* **DynamoDB**: derived data only (exercise repertoire, trends, metadata, equipment profile)
* **Invariant**: DynamoDB fully rebuildable from Hevy + S3

---

## Failure Modes to Avoid

* Reacting to single workouts
* Over-introducing new exercises
* Easy path selection by user
* Frequent belief updates
* Mid-session re-planning without intent

---

## End State Vision

A Slack-native coaching system that:

* Holds clear, defensible training opinion
* Applies weekly pressure
* Guides session execution
* Evolves slowly but decisively
* Feels like a real coach, not a stats dashboard
