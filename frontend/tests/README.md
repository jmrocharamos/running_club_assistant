# Demo reliability checks

Run from `frontend`:

```sh
npm test
npm run lint
npx tsc --noEmit
npm run build
```

The tests render the dashboard and chat widget with real React Query providers,
mocking API boundaries. They verify failed reads, retry recovery, legitimate
onboarding, blocked chat actions during a history failure, and API error mapping.
No live AI calls are made.

Run backend regression tests from `backend` with the `running_club_test` database
available:

```sh
.venv/bin/pytest
```

Before presenting, rehearse login → dashboard → open plan → generate → feedback
→ revise an active plan → chat → reload and confirm persistence. Also try revising
a finished plan with feedback: it should display a clear finished-plan message.

For browser recovery checks, block the survey, recommendations, or chat-history
request using DevTools, reload, and confirm an error appears. Unblock the request
and click retry. Confirm saved data returns. Remove request blocking afterward.

A timeout does not guarantee the backend stopped generating. Check the plan list
before retrying generation. Automated tests simulate timeouts without making live
AI requests; they do not measure model latency or recommendation quality.
