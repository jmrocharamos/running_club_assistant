# Running Club Assistant — Frontend

A Next.js frontend for the Running Club Assistant AI coaching backend. Lets a
runner complete a training survey, generate an AI running plan, track and
rate plans, leave feedback and request revisions, manage their profile, and
chat with an AI coach.

## Stack

- **Next.js 16** (App Router, Turbopack)
- **TypeScript**
- **Tailwind CSS v4**
- **shadcn/ui** on **Base UI** primitives (not Radix — this repo's shadcn
  setup uses `@base-ui/react`, which has some API differences from the more
  common Radix-based shadcn: polymorphism uses a `render` prop instead of
  `asChild`, and `Select.Value` needs an explicit render function to show a
  label instead of the raw stored value)
- **TanStack Query** for server state, caching, and mutations
- **React Hook Form + Zod** for the survey and profile forms
- **Lucide** icons

## Getting started

```bash
npm install
cp .env.example .env.local   # adjust NEXT_PUBLIC_API_BASE_URL if needed
npm run dev
```

The app runs at `http://localhost:3000` and expects the FastAPI backend at
`http://127.0.0.1:5002` (see `backend/README` / `backend/app/main.py`).

```bash
npm run build   # production build
npm run start   # serve the production build
npm run lint    # eslint
npx tsc --noEmit  # typecheck
```

## Environment variables

| Variable | Description |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the FastAPI backend. Defaults to `http://127.0.0.1:5002`. |

## Architecture

```
src/
  app/
    login/                  public — sign in
    register/               public — create an account
    forgot-password/        public — request a reset link
    reset-password/         public — set a new password
    (app)/                  protected route group, wrapped in AuthGuard + AppShell
      dashboard/
      survey/               survey history
        new/                create a new survey
        [id]/               read or delete a survey
      plans/
        [id]/               plan detail: rating, favorite, feedback, regenerate
      favorites/
      coach/
      profile/
  components/
    app-shell/               sidebar, mobile drawer nav, header
    auth/                    authentication forms and AuthGuard
    providers/                SessionProvider, QueryProvider, AppProviders
    plans/                    RecommendationCard/List, StarRating, FavoriteButton,
                               GeneratePlanButton, RegenerateSection, plan rendering
    survey/                   multi-step wizard + reusable field components
    feedback/                 FeedbackForm, FeedbackList
    chat/                     ChatMessage, ChatComposer
    ui/                       shadcn/Base UI primitives
  hooks/                      one hook per resource (surveys, recommendations,
                               feedback, current user) wrapping TanStack Query
  lib/
    api/                      client.ts (fetch wrapper + error normalization)
                               + one file per resource (users, surveys,
                               recommendations, feedback, chat)
    validation/                zod schemas mirroring backend Pydantic schemas
    auth-events.ts             shared unauthorized-session events
    survey-options.ts          label maps for backend enums
    query-keys.ts               centralized TanStack Query keys
  types/                       TypeScript types mirroring backend schemas 1:1
                                (same field names, snake_case, no invented fields)
```

### API layer

All HTTP calls go through `lib/api/client.ts`, which centralizes the base
URL, JSON handling, and error normalization into a typed `ApiError` (`kind`:
`validation | not_found | conflict | bad_request | server | network`). Every
resource (`users`, `surveys`, `recommendations`, `feedback`, `chat`) has its
own thin wrapper file — no `fetch()` calls happen directly in components.

### Types

Types in `src/types/` mirror the backend's Pydantic schemas field-for-field
(same names, same optionality). Nothing is invented; anything not present in
a backend schema (e.g. structured `social_media` editing) is intentionally
left out of the UI rather than faked.

## Authentication

The backend verifies Argon2 password hashes and issues a signed JWT in an
HTTP-only cookie. The browser sends that cookie automatically because the API
client uses `credentials: "include"`; authentication tokens are never stored
in localStorage or exposed to application JavaScript.

The public workflow includes registration, login, forgot password, and reset
password. Authenticated runners can also change their password from their
profile. `SessionProvider` restores the session through `GET /auth/me`, while
`AuthGuard` protects application pages. Backend routes derive ownership from
the authenticated user instead of accepting an arbitrary user ID from the
browser.

Password-reset email delivery currently uses a local console sender. In local
development, the reset URL appears in the FastAPI terminal rather than being
sent to a real inbox.

## Backend integration

The frontend uses authenticated, current-user endpoints for profiles,
surveys, recommendations, feedback, and coach chat. FastAPI validates the JWT
cookie and checks resource ownership before returning or changing user data.
AI generation and revision failures are returned as structured API errors;
the revision safety gate can request more health information or pause a plan
for coach review.

## Notable design decisions

- **Survey is a 5-step wizard**, not a single long form, mirroring the
  size and complexity of `RunningPlanSurveyAnswers` (24 fields with several
  cross-field constraints — training days must include the long-run day and
  cover `runs_per_week`, `available_equipment`/`current_issue_areas` can't
  combine "none" with other options, etc.). Those constraints are
  re-implemented client-side in `lib/validation/survey.ts` with a Zod
  `superRefine`, matching the backend's Pydantic `model_validator`.
- **Surveys are historical records.** Runners create a new survey instead of
  editing an earlier one in place. The history page shows prior surveys, and
  deletion is soft so existing recommendations keep their source snapshot.
- **Regenerating from feedback** surfaces the backend's safety gate exactly:
  a `needs_health_update` response opens the structured health-update dialog,
  and a `requires_coach_review` response shows a static "paused for human
  review" message — no client ever second-guesses that gate.
- **RAG/knowledge-base internals are not exposed.** The chat UI only ever
  shows `reply` text; embeddings, retrieved chunks, and Langfuse are
  entirely backend-internal.
- **Favorites are a real page**, backed by the authenticated recommendations
  endpoint rather than a client-side-only filter.

## Known gaps / things a backend engineer should know

- Shoe recommendations (`RecommendationType.SHOE_RECOMMENDATION`) are
  defined in the survey schema but have no prompt/service implementation on
  the backend, so the frontend only builds the running-plan survey flow.
- `social_media` (`dict[str, Any]` on `User`) has no structured UI — there's
  no reasonable generic editor for an arbitrary JSON blob, so it's left
  out of the Profile form rather than faked.

## Vercel deployment

Import the repository with `frontend` as the Root Directory and Next.js as the
framework. Set these variables for the Production environment before building:

```dotenv
NEXT_PUBLIC_API_BASE_URL=/api
API_BACKEND_URL=https://running-club-assistant-api.onrender.com
```

The browser calls `/api/...`; Next.js forwards requests to FastAPI while keeping
cookies on the frontend domain. The page authentication proxy lets `/api` requests
through so FastAPI handles authentication and returns JSON errors. Do not point
`NEXT_PUBLIC_API_BASE_URL` directly at Render: its host-only cookies would not be
available to the frontend's page authentication checks.

After Vercel assigns the production URL, set `FRONTEND_BASE_URL` on Render to that
URL and keep `ENVIRONMENT=production`. Rebuild Vercel after changing either API
URL variable. Keep OpenAI, Langfuse, database, and JWT credentials on Render only.

Verify login, a page reload, and logout on the deployed frontend. Check
`/api/users/me` returns JSON 401 before login. Knowledge indexing is a separate
production setup step; database migrations do not populate the knowledge base.
