# Local AI verification — 7 October 2026

Tested `qwen3.5:9b` generation and `qwen3-embedding:0.6b` retrieval through
Ollama on the local 32 GB Mac. The application retains OpenAI as its source
configuration default; the ignored local `.env` selects Ollama for both.

## Results

| Check | Result |
| --- | --- |
| Backend regression suite | 110 tests passed |
| OpenAI chat baseline using Ollama retrieval | 8/8 heuristic cases passed |
| Initial Ollama evaluation | 16/21 heuristic cases passed |
| Revised Ollama chat, memory, and safety | 18/18 heuristic cases passed |
| Revised normal and walking-only four-week plans | 2/2 heuristic cases passed |
| Live authenticated API journey | Passed chat/history, summary, saved plan/readback, feedback/revision, and blocked-injury generation |
| Fully local app import with an empty OpenAI key | Passed without importing the OpenAI client |

The live API journey ran in an isolated PostgreSQL schema inside a rolled-back
transaction. Synthetic accounts, conversations, surveys, feedback, and plans
were not left in the application database. The normal revision preserved dates
and saved a new plan rather than overwriting the original.

## Changes driven by failures

- The local model repeated a stored marathon goal and morning preference in a
  greeting. The chat prompt now gives an explicit greeting rule and example;
  the revised case passed.
- The normal plan had correct dates but capitalized weekday labels. The app
  now derives canonical weekday labels from dates.
- The adapted plan included unavailable weekdays. Initial generation now
  receives an authoritative calendar, validates dates and week boundaries,
  and allows one correction attempt before rejecting invalid output. Both
  revised plan cases used eight sessions on the supplied available dates.
- Two safety cases took more restrictive paths than requested by the existing
  application policy: blocking explicitly cleared walking and routing a
  free-text concern directly to coach review. Clarified, versioned safety
  prompts produced the intended modes and health-update routing on rerun.
- Contradictory feedback decisions and plan modes are rejected by schema
  validation for both providers.

## Practical limits

Revised four-week plan calls took about 146 seconds each on this machine.
Chat evaluation timings increased when a long plan request was running at the
same time; run comparisons sequentially for useful latency measurements.
The existing synchronous HTTP flow can still time out through a proxy during
long generation or correction. No background-job architecture was added.

These are small synthetic evaluations with heuristic checks and manual review,
not a comprehensive assessment of coaching or clinical quality. Longer plans,
larger histories, additional clearance scenarios, and concurrent load remain
future evaluation work. Running duration cannot be checked numerically with
the current running-block schema.

## Reproduce

From `backend`, run these sequentially:

```bash
.venv/bin/pytest -q
.venv/bin/python -m scripts.evaluate_ai --provider openai --workflows chat
.venv/bin/python -m scripts.evaluate_ai --provider ollama --workflows all
```

The OpenAI command incurs usage. Live reports are saved under the ignored
`backend/evaluation/results/` directory and include synthetic output for review.
See [local model configuration](LOCAL_MODELS.md) for provider switching.
