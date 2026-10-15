# Anonymous OpenAI demo

The demo uses the existing users, surveys and coach-memory tables. No schema
migration is needed. Each visitor receives a server-created temporary runner,
a fictional profile and a four-week sample survey. Existing ownership checks
isolate their plans, feedback and chats from every other user.

Enable locally with `DEMO_ENABLED=true` in `backend/.env`, then restart the API
and open `/demo` in the frontend. The login page links there. Production remains
unchanged until these changes are committed, deployed and explicitly enabled in
Render. The flag defaults to false. Do not expose an API key in frontend env vars.

The limits are 15 minutes, five chat messages, one initial plan attempt, one
revision attempt and one end-chat summary. Failed AI requests count as attempts.
Safety assessments and one permitted correction are part of the existing plan
and revision workflows. The normal application validators remain in place.
Demo surveys cannot request more than four weeks. Demo requests always select
OpenAI for responses and embeddings, independently of local account settings.

The signed access token and stored expiry enforce the deadline. Refreshing or
resuming an active demo does not reset it. OpenAI calls use the remaining time
as their timeout and disable SDK retries. A database commit guard rejects late
writes, and an expired response cannot return the generated result. The browser
countdown is informational; it is not the access-control mechanism.
Per-call output is also capped: 1,024 tokens for chat, 4,096 for summaries,
16,000 for plans/revisions, and 2,048 for safety assessments. Truncated output
fails validation and consumes the attempt; it is not silently retried.

Usage is reserved under a database advisory lock before endpoint work and
committed before the AI call, so errors cannot repeatedly refund attempts.
Non-status protected requests are also capped at 250 per session. Starting demos
is limited to three per browser per hour, 20 total starts per hour and five
concurrently active sessions. A signed, HttpOnly `demo_browser` cookie identifies
the browser; only an HMAC of its random identifier is stored in the database.
It cannot authenticate a user. This avoids grouping unrelated visitors behind
the website's deployment proxy. Clearing cookies can reset the per-browser
limit, but the global limits still apply. These limits bound access, not a monetary billing cap or bot-proof
identity check. Account creation remains a separate existing app flow.

While demo mode is enabled and the API is running, housekeeping runs at startup
and every minute. At expiry it removes temporary chat, survey, plan and feedback
content. A minimal anonymous rate-limit record and synthetic user identity remain
until one hour after creation, then are deleted. Sleeping or stopped services
purge on their next startup. Keep demo mode enabled until the last session has
been cleaned, or run `demos.cleanup` with an application database session before
disabling housekeeping. Access is denied immediately at expiry even if cleanup
has not run yet.

Demo users cannot change profile/account/password settings. Temporary identities
cannot log in with a password or receive reset emails. An existing signed-in
account is never replaced by Start demo; use a private window for testing.
Creating an account after the demo starts a fresh permanent workspace; this
version does not copy demo data into that account.

The browser selector and hosted Ollama are later steps. This version deliberately
offers the demo with OpenAI only. Verification covers deterministic authorization,
limits, cleanup, expiry, sample workflows and UI behavior with mocked AI calls.
Live model quality, browser walkthrough and deployment checks remain separate.
