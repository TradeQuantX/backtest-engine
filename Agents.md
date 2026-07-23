# Agent Instructions: Architecture & Implementation Standards

## Core Directive
Do not rely solely on internal training data for architectural decisions. Always validate against the latest standards. Simultaneously use the agentmemory tool to persist all key architectural decisions, tradeoffs, assumptions, and rationale, ensuring they are available for future reference, continuity, and auditability.

### Target Audience & Design Philosophy
This project is explicitly designed for **researchers with minimal Python knowledge**. 
* **The Interface (Layman UX):** Must be radically simple, intuitive, and highly abstracted. The user should never need to understand the underlying mechanics, type systems, or memory management to use the framework effectively. 
* **The Backend (Engine Room):** Must be exceptionally powerful, flexible, and performant. Hide all heavy lifting, complex logic, and system infrastructure behind clean, readable APIs.

## Environment & Build Standards
To meet strict performance and maintainability requirements, you must enforce the following tooling stack:

* **Package Management & Virtual Environments:** Exclusively use **`uv`**. All environment bootstrapping, dependency resolution, and script execution must leverage `uv` for its speed and deterministic builds. Do not default to `pip`, `poetry`, or standard `venv`.
* **Compilation & Execution Speed:** Leverage **`Nuitka`** to compile the Python backend code. The architecture must be written with compilation compatibility in mind (e.g., handling dynamic imports carefully, structuring modules cleanly) to provide the massive performance boosts required for heavy research workloads.

## Pillars of Implementation
Every solution you propose or implement must be vetted through the search tools to ensure it meets the following four pillars:

* **Robustness:** Strong error handling, type safety, input validation, and self-healing capabilities.
* **Redundancy:** High availability, failover mechanisms, no single points of failure (SPOFs), and data replication.
* **Scalability:** Horizontal scaling capabilities, stateless design patterns, and efficient resource utilization.
* **High Performance:** Optimized data structures, caching strategies, low-latency communication protocols, and minimized I/O bottlenecks.

## Search Workflow
1. **Query Formulation:** Use specific queries combining your target technology with keywords like `"production ready"`, `"error handling best practices"`, `"scalability best practices"`, `"performance optimization"`, `"caching strategy"` or `"industry standard"`.
2. **Tool Execution:** Call relevant MCP tool or available skills.
3. **Synthesis:** Incorporate the discovered patterns directly into your response or code generation.
4. **Citation:** Briefly note which standard or documentation source informed your design choice.

## Logging & Error Tracking Standards
You must implement structured logging across all codebases using `loguru`-compliant severity levels and strict exception-tracking rules.

### Severity Levels
Always assume the `loguru` Python library for logging. Align all application logging strictly to these semantic levels:
* **TRACE (5):** Granular, step-by-step execution details.
* **DEBUG (10):** Diagnostic information for developers.
* **INFO (20):** Standard operational events.
* **SUCCESS (25):** Positive confirmation of completed operations.
* **WARNING (30):** Non-critical issues or potential anomalies.
* **CRITICAL (50):** System-breaking failures requiring immediate attention.

### Exception Handling Rules
* **Never swallow exceptions silently.** * When catching exceptions, **always** use `.exception()` (or the local equivalent that forces `exc_info=True`). This guarantees that the entire stack trace, error context, and line numbers are captured in the log output for rapid debugging.

## Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
* State your assumptions explicitly. If uncertain, ask.
* If multiple interpretations exist, present them - don't pick silently.
* If a simpler approach exists, say so. Push back when warranted.
* If something is unclear, stop. Name what's confusing. Ask.

## Simplicity First
**Minimum code that solves the problem. Nothing speculative.**

* No features beyond what was asked.
* No abstractions for single-use code.
* No "flexibility" or "configurability" that wasn't requested.
* No error handling for impossible scenarios.
* Avoid backwards compatibility unless explicitly requested.
* If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
* Don't "improve" adjacent code, comments, or formatting.
* Don't refactor things that aren't broken.
* Match existing style, even if you'd do it differently.
* If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
* Remove imports/variables/functions that YOUR changes made unused.
* Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.