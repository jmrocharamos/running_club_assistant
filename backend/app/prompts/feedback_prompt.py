from app.prompts.running_plan_prompt import ADAPTED_MODE_RULES, PLAN_LANGUAGE_RULES

REMAINING_PLAN_FEEDBACK_PROMPT = """
Revise the currently selected running plan using all feedback attached to it.

Priority: safety, newest feedback, selected plan, then survey snapshot.

Rules:

- Return only the remaining period from revision_date onward.
- The dates in REMAINING PLAN are already final. Return every training day
  and weekly distance entry using exactly the same date, day, start_date, and
  end_date values as given in REMAINING PLAN — do not shift, invent, or
  recompute any date, even if feedback mentions a schedule change.
- Use the selected plan as the baseline; do not rebuild it from scratch.
- Make only changes requested by feedback or required for safety.
- Preserve all unrelated content.
- Do not restore removed or absent features unless current feedback requests it.
- Add strength or mobility to existing training days unless feedback explicitly
  requests additional days.
- If stable training is requested, keep load stable across remaining full weeks.
- Reduce load when feedback says the plan is too difficult.
- Increase load only when explicitly requested and safe.
- Newest feedback wins when entries conflict.
- Never invent dates, runner facts, completed sessions, health information,
  equipment, availability, or preferences.
- Each weekly distance must equal its returned running-session distances.
- Return the required structured running-plan output with only remaining weeks
  and training days.
"""


ADAPTED_REMAINING_PLAN_FEEDBACK_PROMPT_V1 = """
Revise the remaining portion of the selected plan using the supplied safety
contract and chronological feedback.

Priority:

1. Safety contract and required plan mode
2. Newest feedback
3. Remaining selected plan
4. Historical survey snapshot

Schedule:

- Return only the remaining period from revision_date onward.
- Return every supplied training date exactly once.
- Keep every date, day, week number, week start, and week end unchanged.
- The dates in REMAINING PLAN are already final.
- Do not add, remove, shift, or recompute dates.
- A running day may become walking or support-only when required for safety.

Adaptation:

- Treat the required plan mode as a hard upper boundary.
- Redesign the complete weekly structure instead of mechanically converting
  every running session into the same easier activity.
- Decide how many locomotion sessions remain appropriate.
- Replace unsafe sessions with walking, gentle strength, mobility, or recovery
  work allowed by the selected mode.
- For each full week that originally contains more than three running sessions,
  reduce locomotion sessions by at least one and convert at least one supplied
  date into mobility, gentle strength, stability, or recovery-only work.
- Do not redistribute the removed distance into the remaining sessions.
- Remove races, speedwork, intervals, tempo, threshold, hills, and hard efforts.
- Never restore an activity removed by newer feedback.
- Do not describe strength or mobility as injury treatment or rehabilitation.
- Use only the runner's available equipment.
- Explain important replacements in training-day notes.

Load:

- Do not preserve the previous weekly distance as a target.
- When locomotion sessions are removed, reduce total distance.
- Never redistribute removed distance into remaining sessions.
- Keep adapted load stable or use only very small safe progression.
- Weekly distance must equal running plus walking distance for that week.
- Strength and mobility do not contribute to distance.

Output:

- Follow the application's structured running-plan schema.
- Return only remaining weeks and training days.
- Keep safety notes concise and specific.
- Explain how the revised weekly structure follows the required mode.
"""


def get_feedback_prompt(version: str = "remaining") -> str:
    prompts = {
        "remaining": REMAINING_PLAN_FEEDBACK_PROMPT,
    }

    if version not in prompts:
        raise ValueError(
            f"Unknown feedback prompt version: {version}"
        )

    return f"{prompts[version].strip()}\n\n{PLAN_LANGUAGE_RULES.strip()}"


def get_adapted_feedback_prompt(
        plan_mode: str,
) -> tuple[str, str]:
    mode_rules = ADAPTED_MODE_RULES.get(
        plan_mode
    )

    if mode_rules is None:
        raise ValueError(
            f"Unsupported adapted plan mode: {plan_mode}"
        )

    instructions = (
        f"{ADAPTED_REMAINING_PLAN_FEEDBACK_PROMPT_V1.strip()}\n\n"
        f"{mode_rules.strip()}\n\n"
        f"{PLAN_LANGUAGE_RULES.strip()}"
    )

    return "remaining_adapted1", instructions
