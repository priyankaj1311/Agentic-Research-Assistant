# Agentic Research Assistant

A production-quality, multi-step agentic research system built in Python with **LlamaIndex**, **Tavily**, and **OpenAI**.

Given a complex research question the system autonomously plans the investigation, launches parallel sub-researchers, searches the web, reads and compresses sources, assesses coverage, fills identified gaps, and produces a structured Markdown report with inline citations.

---

## Architecture

```
User Question
      ↓
Scope Agent          → research brief
      ↓
Research Planner     → focused subtopics
      ↓
 ┌─────────────────────────────────────────┐
 │  Parallel Sub-Researchers (async)        │
 │  ┌─────────────────────────────────┐    │
 │  │  ReActAgent (isolated context)  │    │
 │  │  ├─ search_web (Tavily)         │    │
 │  │  ├─ read_url (compress → LLM)   │    │
 │  │  └─ reflect (think tool)        │    │
 │  │          ↓                      │    │
 │  │  Compressed Cited Summary       │    │
 │  └─────────────────────────────────┘    │
 └─────────────────────────────────────────┘
      ↓
Shared Research Notes (compressed only)
      ↓
Coverage / Gap Assessment
      ├── gaps? → Additional Research Round (bounded)
      └── sufficient → Final Writer
                           ↓
                    Structured Markdown Report
```

### Key architectural property: context isolation

Each sub-researcher operates in a fully isolated coroutine.  Search results, raw webpage content, and agent conversation history never leave the researcher's scope.  Only the compressed cited summary (200–500 words) is returned to the shared state and passed to the final writer.

---

## Project Structure

```
agentic-research-assistant/
│
├── app/
│   ├── config.py                  # All settings, driven by env vars
│   ├── models/
│   │   ├── state.py               # ResearchState, ResearchNote (Pydantic)
│   │   └── schemas.py             # Structured LLM output models
│   ├── workflow/
│   │   ├── research_workflow.py   # LlamaIndex Workflow (steps + events)
│   │   ├── planner.py             # Scope Agent + Research Planner
│   │   ├── orchestrator.py        # Parallel researcher dispatcher
│   │   ├── researcher.py          # Isolated ReActAgent sub-researcher
│   │   ├── critic.py              # Coverage / Gap Assessment
│   │   └── writer.py              # Final report synthesis
│   ├── tools/
│   │   ├── tavily_search.py       # Tavily web search tool
│   │   ├── read_url.py            # URL fetch + question-focused compression
│   │   └── think.py               # Researcher reflection tool
│   ├── services/
│   │   ├── llm.py                 # LLM factory (role-based model selection)
│   │   ├── source_reader.py       # HTML/PDF extraction + LLM compression
│   │   └── citation.py            # Citation extraction utilities
│   └── utils/
│       ├── retry.py               # Exponential back-off helpers
│       ├── logging.py             # Structured logging (structlog)
│       └── limits.py              # Budget enforcement
│
├── tests/
│   ├── conftest.py
│   ├── test_planner.py            # Scope + subtopic generation
│   ├── test_researcher.py         # Isolated researcher + context isolation
│   ├── test_tools.py              # Tavily, ReadURL, Reflect tools
│   ├── test_workflow.py           # Parallelism, gap loop, failure recovery
│   └── test_citations.py          # Citation preservation end-to-end
│
├── main.py                        # CLI entry point
├── requirements.txt
└── .env.example
```

---

## Installation

```bash
# 1. Clone / download the project
cd agentic-research-assistant

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API keys
cp .env.example .env
# Edit .env and set OPENAI_API_KEY and TAVILY_API_KEY
```

---

## Usage

```bash
# Basic usage
python main.py "How is generative AI changing customer service in banking?"

# Save report to a file
python main.py --output report.md "What are the major risks of LLMs in finance?"

# Using the --query flag
python main.py --query "Explain the current state of quantum computing in 2025"
```

---

## Configuration

All limits are environment-variable driven (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `MAX_RESEARCH_ITERATIONS` | `2` | Maximum gap-fill research rounds |
| `MAX_CONCURRENT_RESEARCHERS` | `5` | Parallel researcher cap |
| `MAX_RESEARCHER_STEPS` | `20` | Agent loop iteration limit |
| `MAX_SEARCH_RESULTS` | `10` | Tavily results per search |
| `MAX_CONTENT_LENGTH` | `50000` | Raw page char limit before compression |
| `MAX_LLM_CALLS` | `30` | Hard LLM call budget |
| `MAX_RETRIES` | `3` | Retry attempts with exponential back-off |
| `SCOPE_MODEL` | `gpt-4o` | Model for scoping + planning |
| `RESEARCHER_MODEL` | `gpt-4o-mini` | Model for research loops |
| `PAGE_SUMMARIZER_MODEL` | `gpt-4o-mini` | Model for page compression |
| `WRITER_MODEL` | `gpt-4o` | Model for final synthesis |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## LLM Context Rules (enforced by design)

1. Raw webpages never reach the final writer.
2. Researcher conversation histories never reach the orchestrator.
3. All search results from all researchers are never merged into one prompt.
4. Only compressed researcher summaries enter shared state.
5. The writer receives: research brief + compressed notes — nothing else.
