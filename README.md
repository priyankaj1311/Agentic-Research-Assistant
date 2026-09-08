# Agentic Research Assistant

A multi-agent research system that takes a natural-language question, plans it into focused subtopics, dispatches isolated sub-researchers in parallel to search and read the web, judges whether coverage is sufficient, fills gaps if not, and synthesizes a cited Markdown report — with two optional human-in-the-loop checkpoints along the way.

Built on [LlamaIndex Workflows](https://docs.llamaindex.ai/en/stable/module_guides/workflow/) (`llama_index.core.workflow`), OpenAI models, and [Tavily](https://tavily.com/) for web search.

---

## Why this exists

Naive "agentic RAG" systems tend to dump everything — every search result, every scraped page, every sub-agent's full conversation — into one growing prompt until the context window explodes and answer quality degrades. This project is built around a single architectural rule instead:

> **Raw content never crosses an agent boundary. Only compressed, cited summaries do.**

Concretely:
- A sub-researcher can search and read as many pages as it needs *internally*, but only returns one short, cited summary (a `ResearchNote`) to the shared state.
- The final writer never sees raw web pages — only the compressed notes.
- Nothing is merged into one giant prompt across researchers; each runs in its own isolated coroutine with no shared mutable state during execution.

## Pipeline overview

```
User Question
  → scope()            LLM turns the question into a structured research brief
  → plan()              LLM decomposes the brief into ~5 focused, non-overlapping subtopics
  → review_plan()        [HITL #1 — optional] user can add/edit/remove subtopics before research starts
  → run_research()       parallel sub-researchers, one per subtopic (bounded concurrency)
  → assess_and_route()   LLM critic judges coverage: sufficient, or name concrete gaps
        ├─ gaps + iterations/steps remaining → loop back into run_research() with gap subtopics
        └─ sufficient, or limits reached      → review_sources()
  → review_sources()     [HITL #2 — optional] user can exclude specific cited sources
        ├─ exclusion drops coverage below sufficient → targeted re-research on the new gap
        └─ approved / round limit reached             → write()
  → write()               LLM synthesizes the final Markdown report from the compressed notes only
```

Each sub-researcher internally runs its own bounded agent loop:

```
FunctionAgent(tools=[search_web, read_url, reflect], llm=gpt-4o-mini)
  → call LLM with tool schemas + history
  → LLM requests tool call(s) (parallel tool calls allowed)
  → execute tool(s), append results to history
  → repeat until the LLM returns plain text (no more tool calls) or max_iterations is hit
  → agent's raw answer is compressed a second time before leaving the researcher's scope
```

## Project structure

```
main.py                          CLI entry point (asyncio.run, 10-minute hard timeout)
app/
  config.py                      pydantic-settings config, env-driven
  models/
    state.py                     ResearchState (shared, mutated only after parallel rounds complete),
                                  ResearchNote (per-researcher compressed output)
    schemas.py                   structured LLM outputs: ResearchBrief, SubtopicPlan, CoverageAssessment
  workflow/
    research_workflow.py         the Workflow: steps, events, routing, budget guard
    planner.py                   scope() and plan_subtopics()
    orchestrator.py               run_parallel_researchers() — bounded async fan-out
    researcher.py                 isolated sub-researcher (FunctionAgent + 3 tools + 2nd compression pass)
    critic.py                     assess_coverage() — sufficiency/gap judgment
    writer.py                     final report synthesis
    hitl.py                       review_plan_hitl(), review_sources_hitl(), recompress_without_sources()
  tools/
    tavily_search.py              search_web tool (Tavily, domain filtering, retry)
    read_url.py                   read_url tool (fetch + domain filter + question-focused compression)
    think.py                      reflect tool — pure formatting function, no external calls
  services/
    llm.py                        get_llm(role) — cached per-role OpenAI clients
    source_reader.py               fetch_and_extract() (HTML/PDF), compress_for_research()
    citation.py                    markdown citation regex utilities
  utils/
    retry.py                      sync_retry / async_retry, exponential backoff
    logging.py                    structlog setup
    limits.py                     ResearchBudget class — defined but currently unused (see Known Issues)
tests/
  test_planner.py, test_researcher.py, test_workflow.py, test_tools.py, test_citations.py, conftest.py
```

## Setup

```bash
git clone https://github.com/priyankaj1311/Agentic-Research-Assistant
cd Agentic-Research-Assistant
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY and TAVILY_API_KEY
```

`.env` is git-ignored and never committed — `.env.example` is a template only. Whatever values you set locally are what actually govern a run; unset values fall back to the class defaults in `app/config.py` (which are not always identical to `.env.example` — see Known Issues).

## Usage

```bash
python main.py "How is generative AI changing customer service in banking?"
python main.py --query "..." --output report.md
```

During a run you'll be prompted twice (unless HITL is disabled/skipped in your config):
1. **Plan review** — the generated subtopics are printed; you can `add`, `edit <n>`, `remove <n>`, or approve with a blank line.
2. **Source review** — every cited URL is listed (deduped, cross-referenced to which subtopic(s) cited it); you can `exclude <n,n,...>`, force synthesis now with `write`, or approve with a blank line.

## Configuration reference

All settings are environment-driven via `pydantic_settings.BaseSettings` in `app/config.py`.

| Variable | Effective default (`.env.example`) | Governs |
|---|---|---|
| `OPENAI_API_KEY` | — | required |
| `TAVILY_API_KEY` | — | required |
| `SCOPE_MODEL` | `gpt-4o` | research brief generation |
| `ORCHESTRATOR_MODEL` | `gpt-4o` | subtopic planning + coverage/gap assessment |
| `RESEARCHER_MODEL` | `gpt-4o-mini` | sub-researcher agent loop |
| `PAGE_SUMMARIZER_MODEL` | `gpt-4o-mini` | page compression + post-agent note compression |
| `WRITER_MODEL` | `gpt-4o` | final report synthesis |
| `MAX_RESEARCH_ITERATIONS` | 2 | research rounds (initial + gap-fill) before forcing source review |
| `MAX_CONCURRENT_RESEARCHERS` | 5 | parallel sub-researchers in flight at once (asyncio.Semaphore) |
| `MAX_ORCHESTRATOR_STEPS` | 8 | independent backstop on total coverage-assessment calls across the run |
| `MAX_RESEARCHER_STEPS` | 20 | tool-call iterations per researcher's agent loop; also the flat per-researcher cost estimate charged against `MAX_LLM_CALLS` |
| `MAX_SEARCH_RESULTS` | 10 | results returned per Tavily search call |
| `MAX_CONTENT_LENGTH` | 50000 | raw characters of a fetched page kept before compression |
| `MAX_LLM_CALLS` | 30 (`.env.example`) / 200 (`config.py` class default) | run-wide LLM call budget; checked before launching each research round, not after every call |
| `MAX_RETRIES` | 3 | retry attempts (exponential backoff) for search/fetch calls |
| `MAX_SOURCE_REVIEW_ROUNDS` | 3 | caps the HITL source-exclusion loop; forces synthesis past this point |
| `SOURCE_EXCLUDE_DOMAINS` | reddit, quora, blogspot, major social platforms | applied at both Tavily search and `read_url` |
| `SOURCE_INCLUDE_DOMAINS` | none (optional allowlist) | if set, restricts research to listed domains |

**Note on the budget guard:** `MAX_LLM_CALLS` is enforced as a *pre-round* check (`calls_remaining // MAX_RESEARCHER_STEPS` determines how many researchers a round can afford), not a hard per-call ceiling. Since researchers are charged a flat `MAX_RESEARCHER_STEPS` regardless of actual usage, and the critic/writer/HITL-recompression calls aren't gated at all, a run can end up slightly over its nominal budget in practice.

## Design decisions worth knowing

- **No vector database / RAG store.** Deliberately excluded — the problem being solved is agentic web research and context management, not persistent semantic retrieval over a corpus.
- **`FunctionAgent`, not `ReActAgent`**, for sub-researchers. Native OpenAI tool-calling (structured JSON tool requests) instead of text-based Thought/Action/Observation prompting + parsing — more reliable with function-calling-capable models like `gpt-4o-mini`.
- **Two compression layers per researcher**: each fetched page is compressed before entering the agent's context (`read_url` → `compress_for_research`), and the agent's own final answer is compressed *again* after the loop ends, before it becomes the `ResearchNote`.
- **State mutation is strictly sequential.** Sub-researchers run concurrently but are pure functions of their inputs (subtopic, brief, a frozen snapshot of `visited_urls`) — none of them touch `ResearchState` directly. Only after `asyncio.gather()` resolves does a single-threaded loop write the returned notes into shared state. This avoids any need for locking, since nothing is mutated concurrently.
- **One failed researcher doesn't fail the run.** Each researcher call is wrapped individually; failures become a `ResearchNote(status="failed")` rather than aborting the batch.
- **Coverage sufficiency is intentionally lenient** (~70% of key dimensions, not exhaustive) to prevent unnecessary gap-fill rounds.
- **Two independent loop-termination counters**: `iteration` (per-round, reset by research rounds) and `state.orchestrator_steps` (cumulative across the whole run, including HITL-triggered re-assessments) — the second exists because the source-review loop can trigger additional coverage checks that the first counter wouldn't catch.

## Known limitations

- **No independent citation verification.** A researcher is instructed (prompt-level, not code-enforced) to only cite URLs it actually visited; nothing re-fetches a page to confirm a specific claim is actually supported by it.
- **`ResearchBudget` (`app/utils/limits.py`) is currently unused** — the class exists with `charge_llm()`/`charge_search()` methods and a `BudgetExceededError`, but budget enforcement in practice happens via inline arithmetic in `research_workflow.py`, not through this class.
- **Config drift**: `MAX_LLM_CALLS` default differs between `config.py` (200) and `.env.example` (30) — whichever your local `.env` actually sets is what governs a real run.
- **CLI-only, blocking, in-memory.** No persistence of `ResearchState` across runs, no progress streaming to a UI, single hard timeout (10 min) for the entire pipeline.
- **Budget checks are pre-round estimates, not exact.** A researcher is charged a flat cost regardless of how many tool calls it actually used, so the run-wide LLM budget can be overshot in practice.

## Testing

```bash
pytest tests/
```

Coverage includes: subtopic planning (non-empty, multiple focused topics), researcher output shape and citation presence, graceful handling of a failing researcher, context isolation (a researcher's raw agent history never leaks into its returned note), concurrent execution of multiple researchers, the gap-fill loop actually triggering on insufficient coverage vs. skipping straight to the writer on sufficient coverage, and citation-preservation utilities.

## License

*(add your license here)*
