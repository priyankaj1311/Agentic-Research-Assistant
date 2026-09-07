# Agentic Research Assistant — Build Specification

## 1. Project Objective

Build a production-quality **Agentic Research Assistant** in Python that accepts a complex research question, autonomously investigates the web, gathers information from multiple sources, synthesizes findings, identifies gaps, performs additional research when necessary, and produces a structured Markdown report with inline citations.

The implementation must use:

- **Python**
- **LlamaIndex**
- **Tavily**
- **OpenAI APIs**

The architecture should closely follow the **core design pattern of the Haystack Deep Research Agent**, but the implementation must be native to LlamaIndex.

Do not simply create a search → summarize → answer pipeline.

The system must demonstrate genuine agentic research behavior:

```text
User Question
      ↓
Scope / Research Brief
      ↓
Research Planning
      ↓
Parallel Sub-Researchers
      ↓
Search → Read → Think → Summarize
      ↓
Compressed Research Notes
      ↓
Coverage / Gap Assessment
      ↓
Additional Research if Required
      ↓
Final Synthesis
      ↓
Cited Markdown Report
```

---

# 2. Most Important Architectural Principle

The most important requirement is **context isolation and compression**.

Do NOT allow all raw search results, webpages, PDFs, and intermediate reasoning to accumulate in one global LLM context.

Each sub-researcher must have its own isolated working context.

For example:

```text
Researcher A
    ├── search results
    ├── webpages
    ├── extracted content
    ├── reasoning
    └── intermediate observations
             ↓
       SHORT CITED SUMMARY
             ↓
       Shared Research Notes


Researcher B
    ├── search results
    ├── webpages
    ├── extracted content
    ├── reasoning
    └── intermediate observations
             ↓
       SHORT CITED SUMMARY
             ↓
       Shared Research Notes
```

Only the compressed summary leaves the researcher context.

The orchestrator and final writer must NOT receive the researchers' complete message histories.

This is the central context-management strategy used by the Haystack design and must be preserved in our implementation.

---

# 3. Required Components

Implement the following logical components.

## A. Scope Agent

Purpose:

Convert the user's original question into a focused research brief.

Input:

```text
User question
```

Output:

```text
Research brief
```

The brief should clarify:

- What needs to be investigated
- Important dimensions of the question
- Time period, geography, industry, or other constraints where applicable
- What a useful final answer should contain

This should be a relatively small LLM call.

---

# 4. Research Orchestrator

The orchestrator is responsible for managing the overall investigation.

Responsibilities:

1. Read the research brief.
2. Break the investigation into focused, non-overlapping subtopics.
3. Delegate subtopics to independent researchers.
4. Run researchers concurrently where appropriate.
5. Inspect returned summaries.
6. Determine whether the research provides sufficient coverage.
7. Identify missing information.
8. Request additional research when necessary.
9. Stop when sufficient coverage is achieved or limits are reached.

The orchestrator should NOT perform all web research itself.

Its primary role is coordination.

Conceptually:

```text
Research Brief
      ↓
Orchestrator
      ↓
 ┌────────┬────────┬────────┐
 ▼        ▼        ▼
R1       R2       R3
 │        │        │
 ▼        ▼        ▼
Notes    Notes    Notes
 └────────┬────────┘
          ▼
    Coverage Check
          │
      ┌───┴───┐
      │       │
    Gaps    Enough
      │       │
      ▼       ▼
 New RQs    Writer
```

---

# 5. Sub-Researcher

Each sub-researcher investigates exactly one focused research question.

Each researcher must have its own isolated LlamaIndex agent/workflow context.

A researcher should be able to:

```text
Research Question
      ↓
Search
      ↓
Evaluate results
      ↓
Read promising source
      ↓
Think / assess findings
      ↓
Search again if necessary
      ↓
Read another source if necessary
      ↓
Produce compressed summary
```

This is an autonomous loop.

The researcher should decide whether it needs:

- another search
- another source
- deeper reading
- reflection
- or whether enough evidence has been collected

But the loop must be bounded.

---

# 6. Tavily Search Tool

Use Tavily for web search.

The search tool should return source information such as:

```text
title
url
snippet/content
```

Do not blindly pass every search result into subsequent LLM calls.

The researcher should inspect search results and decide which sources are worth reading.

Use a reasonable maximum number of results per search.

Make this configurable.

Suggested default:

```text
max_search_results = 10
```

---

# 7. Read URL Tool

Implement a dedicated tool for reading a webpage.

The important behavior is:

```text
URL
 ↓
Fetch page
 ↓
Extract readable content
 ↓
Limit raw content
 ↓
Summarize content toward the research question
 ↓
Return relevant information to researcher
```

Do NOT pass a huge webpage directly into the researcher's context.

The page-reading operation should perform **question-focused compression**.

For example:

```text
Research question:
"What are the major causes of declining honeybee populations?"

Webpage:
50,000 characters

              ↓

Relevant extracted information:
2,000–4,000 characters

              ↓

Researcher context
```

The exact implementation can use suitable Python HTML/PDF extraction libraries.

Support both:

- HTML webpages
- PDF sources where practical

Make maximum raw content configurable.

Suggested default:

```text
max_content_length = 50000
```

---

# 8. Researcher Reflection

The researcher should have a lightweight reflection mechanism.

The researcher should periodically ask internally:

```text
What have I learned?
What evidence do I have?
What is still missing?
Do I need another source?
Can I answer this sub-question?
```

This can be implemented as a lightweight LLM reasoning step or a dedicated tool/action within the LlamaIndex workflow.

Do not expose hidden chain-of-thought.

Only retain the useful research conclusions.

---

# 9. Researcher Output / Compression

When a researcher finishes, it must NOT return its entire research history.

It must return one concise research summary.

Example:

```text
Research finding:

Global solar capacity additions accelerated significantly in 2024,
driven primarily by China, Europe, and the United States. China
accounted for the majority of new installations.

Sources:
[International Energy Agency](https://...)
[IRENA](https://...)
```

The researcher summary is what gets passed to the orchestrator.

The raw:

- search results
- webpage contents
- intermediate observations
- tool calls
- reasoning history

must remain inside the researcher context.

This compression boundary is mandatory.

---

# 10. Citation Strategy

Follow the same basic citation approach as the Haystack implementation.

Do NOT create a separate citation database or claim-to-source registry.

The researcher itself should include citations in its compressed summary.

For example:

```text
According to the International Energy Agency, renewable
capacity additions reached a record level in 2024
[IEA](https://www.iea.org/...).
```

The citation URL must come from an actual source returned/read during research.

The researcher should never invent a URL.

The citation-containing summary becomes part of shared research notes.

The final writer receives those notes and preserves/uses the citations when producing the final report.

Conceptually:

```text
Source
  ↓
Researcher
  ↓
Cited Summary
  ↓
Shared Notes
  ↓
Writer
  ↓
Cited Report
```

This intentionally follows the Haystack approach rather than introducing a separate citation engine. Haystack's documented deep-research workflow describes the researcher as returning a compressed, cited summary and the writer producing Markdown with inline `[text](url)` citations.

---

# 11. Shared Research State

Create an explicit shared state object.

Do not hide important workflow state inside prompts.

The state should conceptually contain:

```python
ResearchState:
    user_query
    research_brief
    subtopics
    research_notes
    gaps
    iteration
    report
```

Additional metadata can include:

```text
run_id
status
created_at
updated_at
researcher_count
llm_call_count
search_count
```

The exact implementation should use appropriate LlamaIndex state/workflow mechanisms.

The important requirement is:

**Shared state contains compressed research outputs, not raw research contexts.**

---

# 12. Research Notes

Research notes should be a collection of researcher summaries.

Conceptually:

```python
research_notes = [
    "Summary from researcher 1...",
    "Summary from researcher 2...",
    "Summary from researcher 3..."
]
```

Each summary should contain useful source citations.

Do not store enormous raw webpages in this shared list.

The final writer receives:

```text
Research Brief
+
Compressed Research Notes
```

not:

```text
Research Brief
+
every search result
+
every webpage
+
every researcher conversation
```

---

# 13. Coverage / Gap Assessment

After the initial researchers finish, the orchestrator must assess whether the research is sufficient.

Use an LLM-based assessment.

Input:

```text
Research brief
+
compressed research notes
```

Output:

```text
sufficient: true/false
gaps: [...]
```

Example:

```json
{
  "sufficient": false,
  "gaps": [
    "Need evidence from primary government sources",
    "Need data covering 2024–2025",
    "Need comparison with Europe"
  ]
}
```

If gaps exist, the orchestrator should create additional focused research tasks.

---

# 14. Iterative Research Loop

The system must support:

```text
Initial Research
      ↓
Coverage Assessment
      ↓
Are there important gaps?
      │
   Yes│
      ▼
Additional Research
      ↓
Coverage Assessment
      ↓
     ...
      │
     No
      ▼
Final Synthesis
```

However, this loop MUST be bounded.

Suggested configuration:

```text
MAX_RESEARCH_ITERATIONS = 2
```

Do not allow unlimited autonomous research.

---

# 15. Parallel Research

Independent subtopics should run concurrently.

For example:

```text
Question
   ↓
Planner
   ↓
 ┌───────────────┬───────────────┬───────────────┐
 ▼               ▼               ▼
Market Research  Technology      Regulation
Research         Research        Research
 │               │               │
 ▼               ▼               ▼
Summary          Summary         Summary
```

Use Python async/concurrency capabilities or the appropriate LlamaIndex workflow mechanism.

Concurrency must be bounded.

Suggested:

```text
MAX_CONCURRENT_RESEARCHERS = 5
```

Do not create an unbounded number of agents.

---

# 16. Final Writer

Once the orchestrator determines that the research is sufficient, invoke the final writer.

The writer receives:

```text
Research Brief
+
Compressed Research Notes
```

The writer should generate a structured Markdown report.

Suggested structure:

```markdown
# Research Report

## Executive Summary

...

## 1. Topic / Finding

...

## 2. Topic / Finding

...

## 3. Topic / Finding

...

## Key Findings

- ...
- ...
- ...

## Conclusion

...

## Sources

- Source 1
- Source 2
- Source 3
```

Use inline citations throughout the report.

Example:

```markdown
Global renewable capacity additions reached record levels in 2024
[IEA](https://www.iea.org/...).
```

The writer must remain grounded in the supplied research notes.

It should not introduce unsupported facts from its own knowledge.

---

# 17. LLM Context Rules

These rules are mandatory.

### Rule 1

Never send all raw webpages to the final writer.

### Rule 2

Never send complete researcher conversation histories to the orchestrator.

### Rule 3

Never send all search results from all researchers into one giant prompt.

### Rule 4

Raw webpage content should only exist inside the researcher/page-reading context.

### Rule 5

Only compressed researcher summaries should enter shared research state.

### Rule 6

The final writer receives the research brief and compressed notes.

### Rule 7

Every LLM call should have a clearly defined input boundary.

This is specifically intended to prevent the context explosion that affected the previous implementation.

---

# 18. Error Handling

Implement robust error handling.

Failures should include:

- Tavily search failure
- webpage fetch failure
- PDF parsing failure
- LLM timeout
- LLM API failure
- malformed structured output
- researcher failure
- writer failure

A failed researcher should not necessarily terminate the entire research run.

Where appropriate:

```text
Researcher A → success
Researcher B → failed
Researcher C → success
```

The orchestrator should be able to continue and decide whether another researcher is needed.

Implement bounded retries.

Suggested:

```text
MAX_RETRIES = 3
```

Use exponential backoff where appropriate.

---

# 19. Budget / Safety Limits

The system must have configurable limits for:

```text
MAX_RESEARCH_ITERATIONS
MAX_CONCURRENT_RESEARCHERS
MAX_ORCHESTRATOR_STEPS
MAX_RESEARCHER_STEPS
MAX_SEARCH_RESULTS
MAX_CONTENT_LENGTH
MAX_LLM_CALLS
MAX_RETRIES
```

Suggested starting values:

```text
MAX_RESEARCH_ITERATIONS = 2
MAX_CONCURRENT_RESEARCHERS = 5
MAX_ORCHESTRATOR_STEPS = 8
MAX_RESEARCHER_STEPS = 20
MAX_SEARCH_RESULTS = 10
MAX_CONTENT_LENGTH = 50000
MAX_LLM_CALLS = 30
MAX_RETRIES = 3
```

Make these environment/configuration driven rather than hard-coded throughout the application.

---

# 20. Model Roles

Use separate model roles where appropriate.

Conceptually:

```text
Scope LLM
    ↓
Orchestrator LLM
    ↓
Researcher LLM
    ↓
Page Summarizer LLM
    ↓
Writer LLM
```

Use a stronger model for:

- planning
- synthesis

Use a less expensive model where appropriate for:

- researcher loops
- page summarization

Do not make every LLM call use the most expensive model unnecessarily.

Model names must be configurable through environment variables.

---

# 21. LlamaIndex Requirements

The implementation must genuinely use LlamaIndex.

Use LlamaIndex's current workflow/agent capabilities rather than building an ordinary Python pipeline with LlamaIndex only appearing in one utility function.

The architecture should demonstrate:

- LlamaIndex workflows
- LlamaIndex agent/tool mechanisms
- structured outputs where useful
- asynchronous execution where appropriate
- explicit workflow state

Do not replace the architecture with LangGraph.

Do not use Haystack.

Haystack is the architectural reference only.

---

# 22. Suggested Project Structure

Use a clean modular structure similar to:

```text
agentic-research-assistant/
│
├── app/
│   ├── __init__.py
│   │
│   ├── config.py
│   │
│   ├── models/
│   │   ├── state.py
│   │   └── schemas.py
│   │
│   ├── workflow/
│   │   ├── research_workflow.py
│   │   ├── planner.py
│   │   ├── orchestrator.py
│   │   ├── researcher.py
│   │   ├── critic.py
│   │   └── writer.py
│   │
│   ├── tools/
│   │   ├── tavily_search.py
│   │   ├── read_url.py
│   │   └── think.py
│   │
│   ├── services/
│   │   ├── llm.py
│   │   ├── source_reader.py
│   │   └── citation.py
│   │
│   └── utils/
│       ├── retry.py
│       ├── logging.py
│       └── limits.py
│
├── tests/
│   ├── test_planner.py
│   ├── test_researcher.py
│   ├── test_tools.py
│   ├── test_workflow.py
│   └── test_citations.py
│
├── .env.example
├── requirements.txt
├── README.md
└── main.py
```

You may modify the exact structure if LlamaIndex's implementation benefits from another organization, but keep responsibilities clearly separated.

---

# 23. Observability

The application should make the research process inspectable.

At minimum, log:

```text
Research run started
Research brief created
Subtopics generated
Researchers launched
Researcher completed
Sources searched
URLs read
Research summaries generated
Coverage assessment
Additional research triggered
Final synthesis started
Report generated
```

Do NOT log sensitive API keys.

Do not log enormous raw webpage contents by default.

Prefer metadata such as:

```text
researcher_id
subtopic
number_of_sources
number_of_searches
elapsed_time
status
```

---

# 24. Testing Requirements

Create tests for the critical architecture.

At minimum test:

### Planner

Given a broad research question, produces multiple focused subtopics.

### Researcher

Given a subtopic, can search and produce a compressed cited summary.

### Context isolation

Verify that raw researcher history is not passed to the orchestrator.

### URL reading

Verify that large source content is compressed before being returned.

### Parallelism

Verify multiple independent researchers can run concurrently.

### Gap loop

Verify:

```text
insufficient → additional research
```

and:

```text
sufficient → writer
```

### Citation preservation

Verify source URLs from researcher summaries survive into the final report.

### Failure recovery

Verify one failed researcher does not automatically destroy the entire run.

---

# 25. Example Research Run

Use a complex question such as:

> "How is generative AI changing customer service in banking, what technologies are being adopted, what are the major risks, and which banks have publicly deployed these solutions?"

Expected behavior:

```text
User Question
      ↓
Scope
      ↓
Research Brief
      ↓
Planner
      ↓
 ┌──────────────────────────────┐
 │                              │
 ▼                              ▼
AI adoption             Customer-service
in banking              applications
 │                              │
 ▼                              ▼
Researcher              Researcher
 │                              │
 ├─ Tavily                     ├─ Tavily
 ├─ Read sources               ├─ Read sources
 ├─ Think                      ├─ Think
 └─ Summary + citations        └─ Summary + citations
          │                              │
          └──────────────┬───────────────┘
                         ▼
                  Shared Notes
                         ↓
                  Coverage Check
                         ↓
              Missing risk evidence?
                    /          \
                  yes           no
                   ↓             ↓
             New researcher     Writer
                   ↓             ↓
              More notes      Report
```

The final report should contain citations derived from the actual research sources.

---

# 26. What NOT to Build

Do NOT build any of the following as the primary architecture:

```text
User → Tavily → dump results into GPT → answer
```

or:

```text
User → search → scrape 20 pages → one enormous prompt → GPT
```

or:

```text
All researchers → one global conversation history
```

or:

```text
All webpages → vector DB → blindly retrieve → answer
```

A vector database is NOT required for the core research workflow.

Do not introduce Qdrant/Pinecone merely because it is a RAG project.

The key problem being solved is **agentic web research + context management**, not persistent semantic retrieval.

---

# 27. Definition of Done

The project is complete only when a user can submit a complex research question and the system can:

1. Create a focused research brief.
2. Decompose the investigation into subtopics.
3. Launch independent researchers.
4. Search the web using Tavily.
5. Select relevant sources.
6. Read webpages/PDFs when necessary.
7. Compress source information before passing it onward.
8. Keep researcher contexts isolated.
9. Produce cited research summaries.
10. Store only compressed summaries in shared state.
11. Evaluate research coverage.
12. Identify research gaps.
13. Perform additional research when needed.
14. Stop according to explicit limits.
15. Synthesize the findings into a structured report.
16. Preserve source citations in the final report.
17. Handle individual tool/LLM failures gracefully.
18. Provide useful execution logs.
19. Have tests covering the critical workflow behavior.

---

# 28. Critical Implementation Instruction

Before writing the code, first produce a short architecture diagram and explain:

```text
1. What state exists?
2. What belongs to each researcher?
3. What gets passed between researchers/orchestrator/writer?
4. What exactly enters each LLM call?
5. Where does compression occur?
6. How are citations carried forward?
7. How does the research loop terminate?
```

Then implement the system.

Do not change the architecture simply to make implementation easier.

If a LlamaIndex API differs from the conceptual Haystack implementation, adapt the implementation to the equivalent LlamaIndex mechanism while preserving the architecture.

The priority is:

```text
Architecture correctness
      >
Context safety
      >
Research quality
      >
Citation preservation
      >
Production robustness
      >
Implementation convenience
```

The final implementation should be something that can legitimately be described on a professional resume as:

> **Built a multi-step agentic research system capable of planning, researching, synthesizing, and generating structured, citation-backed reports from multiple web sources; implemented autonomous search loops, information extraction, fact synthesis, shared-state workflow orchestration, and iterative research based on identified information gaps.**