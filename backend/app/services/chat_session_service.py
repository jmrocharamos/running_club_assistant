"""Bounded session summaries stored inside the existing coach-memory JSON."""

from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.running_structured_outputs import ChatMemory, ChatSummaryOutput, RunnerMemory

MEMORY_FIELDS = tuple(RunnerMemory.model_fields)
MAX_SAVED_SESSIONS = 10


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def memory_state(coach_memory):
    # Defaults make JSON written by previous app versions readable unchanged.
    return ChatMemory.model_validate(coach_memory.summary.get("chat", {})).model_dump(mode="json")


def save_state(coach_memory, state):
    state["revision"] += 1
    coach_memory.summary = {**coach_memory.summary, "chat": state}


def finish_session(state, output):
    result = ChatSummaryOutput.model_validate(output).model_dump(mode="json")
    user_messages = [message["content"] for message in state["current_conversation"]
                     if message["role"] == "user"]
    evidence = {entry["field"]: entry for entry in result["memory_evidence"]
                if entry["runner_quote"].strip() and any(entry["runner_quote"].strip().casefold() in message.casefold()
                       for message in user_messages)}
    changes = []
    for field in MEMORY_FIELDS:
        if field not in evidence:
            continue
        value = result[field]
        source = evidence[field]
        if source["operation"] == "clear":
            value = [] if isinstance(state[field], list) else None
        elif value is None or value == []:
            # Omitted/empty generated values cannot silently erase prior facts.
            continue
        if isinstance(value, list):
            if source["operation"] == "add":
                value = state[field] + value
            value = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if state[field] != value:
            changes.append({"field": field, "before": state[field], "after": value,
                            "runner_quote": source["runner_quote"]})
        state[field] = value
    # An agreed action must cite an actual runner message, never coach advice.
    steps = []
    seen = set()
    for action in result["next_steps"]:
        quote = action["runner_quote"].strip()
        text = action["text"].strip()
        if (text.casefold() not in seen and quote
                and any(quote.casefold() in message.casefold() for message in user_messages)):
            steps.append({**action, "text": text, "runner_quote": quote,
                          "id": str(uuid4()), "completed": False})
            seen.add(text.casefold())
    session = {
        "id": state["active_session_id"] or str(uuid4()),
        "started_at": state["started_at"], "ended_at": utc_now(),
        "recap": result["recap"].strip() or "No session recap was provided.",
        "next_steps": steps, "open_questions": result["open_questions"],
        "memory_changes": changes,
    }
    state["session_history"] = [session, *state["session_history"]][:MAX_SAVED_SESSIONS]
    state["current_conversation"] = []
    state["active_session_id"] = None
    state["started_at"] = None
    return session
