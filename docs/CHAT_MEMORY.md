# Chat recaps, history and memory controls

All data lives in the existing `coach_memory.summary` JSON column. There are no
new tables, columns or Alembic migrations. Existing four-field chat memories are
read with defaults for the new fields; older completed transcripts cannot be
recovered because the previous End chat flow cleared them.

The `chat` object retains the runner's goal, preferences, topics and reported
progress. It also stores the active conversation, its ID and start time, a
revision number, and the newest ten completed-session summaries. Summaries store
recap text, unresolved questions, agreed actions with completion status, and
before/after memory changes. Full completed transcripts are not retained.

End chat validates the model output and saves the recap and memory together
before clearing active messages. Advisory transaction locks serialize writes for
each runner, including first creation of their memory row. A completed session
ID can be retried without clearing a newer conversation. Editing and deleting
use revision checks so stale browser tabs receive a conflict rather than
overwriting newer data.

Generated memory changes and agreed actions require a quote found in a runner
message. Assistant-only quotations are rejected. Unchanged fields remain intact;
adding list facts preserves previous entries. The model is instructed to treat
replacement/clearing as explicit runner corrections and to distinguish advice
from accepted actions. Quote matching proves attribution, not semantic accuracy;
the runner can review and correct memory, and live model evaluation remains
useful alongside deterministic tests.

History & memory in the chat header allows editing or clearing runner memory,
deleting individual recaps, and marking agreed actions complete. Finish an active
chat before editing memory, so earlier active messages cannot restore a deleted
fact during summarization. Archived recaps are not fed back as runner facts.
Deleting a recap removes its steps but leaves long-term memory intact. Editing
memory leaves recaps intact; delete those separately to remove historical
mentions. When an eleventh session finishes, the oldest recap and its steps are
removed, including any unfinished actions it contained.

Verification uses isolated local PostgreSQL tests and mocked model responses;
it does not send requests to OpenAI, Ollama, Langfuse or production. Run backend
pytest, frontend Vitest, ESLint, TypeScript checking and the Next.js build before
committing. Production deployment and live model checks are separate actions.
