from app.services.telemetry import traced, trace_step
from fastapi import APIRouter, Body, Depends, HTTPException, status
from uuid import uuid4
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.coach_context_service import build_coach_context
from app.services.coach_memory_manager import get_or_create_coach_memory
from app.services.chat_session_service import memory_state, save_state, finish_session, utc_now, MEMORY_FIELDS
from app.services.knowledge_retrieval_service import retrieve_knowledge
from app.services.ai_service import get_chat_reply, summarize_conversation
from app.db.session import get_db
from app.models.user import User
from app.prompts.chatbot_input import build_chatbot_input, build_conversation_summary_input
from app.prompts.chatbot_prompt import get_chatbot_prompt, get_memory_summary_prompt
from app.schemas.chatbot import (
    ChatbotEndResponse,
    ChatbotRequest,
    ChatbotResponse,
    ChatHistoryResponse,
    EndChatRequest, MemoryUpdateRequest, NextStepUpdateRequest,
)
from app.schemas.running_structured_outputs import CoachMemorySummary

router = APIRouter(prefix='/chatbot', tags=['Chatbot'])


def _user_profile(user: User) -> dict:
    return {
        "full_name": user.full_name,
        "interests": user.interests,
        "shoe_size": user.shoe_size,
    }


# Accept the slashless URL used by the frontend proxy without redirecting.
@router.post('', response_model=ChatbotResponse, include_in_schema=False)
@router.post('/', response_model=ChatbotResponse)
@traced("Coach chat", tags=("coach-chat",), workflow=True)
def chat_with_coach(
        chat_data: ChatbotRequest,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Generate a reply using coach memory and retrieved knowledge, then save the exchange."""
    coach_memory = get_or_create_coach_memory(db, current_user.id, lock=True)
    chat_memory = memory_state(coach_memory)
    conversation_history = chat_memory.get(
        "current_conversation",
        [],
    )
    started_at = chat_memory["started_at"] or utc_now()

    coach_context = build_coach_context(
        db,
        current_user,
    )

    instructions = get_chatbot_prompt()

    try:
        knowledge_chunks = retrieve_knowledge(
            db,
            chat_data.message,
        )
        input_text = build_chatbot_input(
            chat_data.message,
            coach_context,
            coach_memory.summary,
            conversation_history,
            knowledge_chunks,
        )
        result = get_chat_reply(
            input_text,
            instructions,
            "simple2",
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Your coach couldn't respond right now. Please try again in a moment.",
        ) from error

    updated_conversation = conversation_history + [
        {"role": "user", "content": chat_data.message},
        {"role": "assistant", "content": result["reply"]},
    ]

    chat_memory["current_conversation"] = updated_conversation
    chat_memory["active_session_id"] = chat_memory["active_session_id"] or str(uuid4())
    chat_memory["started_at"] = started_at
    save_state(coach_memory, chat_memory)

    with trace_step("save_coach_memory"):
        db.commit()
        db.refresh(coach_memory)

    return ChatbotResponse(reply=result["reply"], active_session_id=chat_memory["active_session_id"],
                           revision=chat_memory["revision"])


@router.post('/end', response_model=ChatbotEndResponse)
@traced("Chat memory summary", tags=("coach-chat", "memory-summary"), workflow=True)
def end_chat(
        request: EndChatRequest = Body(default_factory=EndChatRequest),
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    """Save an updated conversation summary and clear the active chat after summarization."""
    coach_memory = get_or_create_coach_memory(db, current_user.id, lock=True)
    chat_memory = memory_state(coach_memory)
    if request.session_id and request.session_id != chat_memory["active_session_id"]:
        completed = next((item for item in chat_memory["session_history"]
                          if item["id"] == request.session_id), None)
        if completed is None:
            raise HTTPException(409, "This chat changed. Refresh before ending it.")
        db.commit()
        return ChatbotEndResponse(summary=CoachMemorySummary(**coach_memory.summary), session=completed)
    conversation_history = chat_memory.get(
        "current_conversation",
        [],
    )

    if not conversation_history:
        db.commit()
        db.refresh(coach_memory)

        return ChatbotEndResponse(
            summary=CoachMemorySummary(**coach_memory.summary)
        )

    instructions = get_memory_summary_prompt()
    input_text = build_conversation_summary_input(
        _user_profile(current_user),
        coach_memory.summary,
        conversation_history,
    )

    try:
        updated_chat_summary = summarize_conversation(
            input_text,
            instructions,
            "sessions-v2",
        )
        session = finish_session(chat_memory, updated_chat_summary)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Your coach couldn't wrap up this session right now. Please try again in a moment.",
        ) from error

    save_state(coach_memory, chat_memory)

    with trace_step("save_coach_memory"):
        db.commit()
        db.refresh(coach_memory)

    return ChatbotEndResponse(
        summary=CoachMemorySummary(**coach_memory.summary), session=session,
    )


@router.get('/history', response_model=ChatHistoryResponse)
def get_chat_history(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    coach_memory = get_or_create_coach_memory(db, current_user.id, lock=True)
    chat_memory = memory_state(coach_memory)

    db.commit()

    return ChatHistoryResponse(
        messages=chat_memory.get("current_conversation", []),
        current_goal=chat_memory.get("current_goal"),
        preferences=chat_memory.get("preferences", []),
        topics_of_interest=chat_memory.get("topics_of_interest", []),
        progress=chat_memory.get("progress"),
        active_session_id=chat_memory["active_session_id"],
        session_history=chat_memory["session_history"], revision=chat_memory["revision"],
    )


def checked_state(db, user, revision):
    memory = get_or_create_coach_memory(db, user.id, lock=True)
    state = memory_state(memory)
    if state["revision"] != revision:
        raise HTTPException(409, "Your saved information changed. Refresh and try again.")
    return memory, state


@router.patch('/memory', response_model=CoachMemorySummary)
def update_memory(request: MemoryUpdateRequest, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    memory, state = checked_state(db, current_user, request.revision)
    if state["current_conversation"]:
        raise HTTPException(409, "End your current chat before editing memory.")
    state.update(request.model_dump(include=set(MEMORY_FIELDS), exclude_unset=True))
    save_state(memory, state)
    db.commit()
    return CoachMemorySummary(**memory.summary)


@router.delete('/sessions/{session_id}', response_model=CoachMemorySummary)
def delete_session(session_id: str, revision: int, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    memory, state = checked_state(db, current_user, revision)
    remaining = [item for item in state["session_history"] if item["id"] != session_id]
    if len(remaining) == len(state["session_history"]):
        raise HTTPException(404, "Session not found.")
    state["session_history"] = remaining
    save_state(memory, state)
    db.commit()
    return CoachMemorySummary(**memory.summary)


@router.patch('/sessions/{session_id}/steps/{step_id}', response_model=CoachMemorySummary)
def update_next_step(session_id: str, step_id: str, request: NextStepUpdateRequest,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memory, state = checked_state(db, current_user, request.revision)
    session = next((item for item in state["session_history"] if item["id"] == session_id), None)
    step = next((item for item in session["next_steps"] if item["id"] == step_id), None) if session else None
    if step is None:
        raise HTTPException(404, "Next step not found.")
    step["completed"] = request.completed
    save_state(memory, state)
    db.commit()
    return CoachMemorySummary(**memory.summary)
