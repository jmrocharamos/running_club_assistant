from app.services.telemetry import traced, trace_step
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.services.coach_context_service import build_coach_context
from app.services.coach_memory_manager import get_or_create_coach_memory
from app.services.knowledge_retrieval_service import retrieve_knowledge
from app.client_openai import get_chat_reply, summarize_conversation
from app.db.session import get_db
from app.models.user import User
from app.prompts.chatbot_input import build_chatbot_input, build_conversation_summary_input
from app.prompts.chatbot_prompt import get_chatbot_prompt, get_memory_summary_prompt
from app.schemas.chatbot import (
    ChatbotEndResponse,
    ChatbotRequest,
    ChatbotResponse,
    ChatHistoryResponse,
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
    coach_memory = get_or_create_coach_memory(db, current_user.id)
    chat_memory = coach_memory.summary.get("chat", {})
    conversation_history = chat_memory.get(
        "current_conversation",
        [],
    )

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
            "simple",
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

    coach_memory.summary = {
        "chat": {
            **chat_memory,
            "current_conversation": updated_conversation,
        },
    }

    with trace_step("save_coach_memory"):
        db.commit()
        db.refresh(coach_memory)

    return ChatbotResponse(reply=result["reply"])


@router.post('/end', response_model=ChatbotEndResponse)
@traced("Chat memory summary", tags=("coach-chat", "memory-summary"), workflow=True)
def end_chat(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    coach_memory = get_or_create_coach_memory(db, current_user.id)
    chat_memory = coach_memory.summary.get("chat", {})
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
            "simple",
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Your coach couldn't wrap up this session right now. Please try again in a moment.",
        ) from error

    coach_memory.summary = {
        "chat": {
            **updated_chat_summary,
            "current_conversation": [],
        },
    }

    with trace_step("save_coach_memory"):
        db.commit()
        db.refresh(coach_memory)

    return ChatbotEndResponse(
        summary=CoachMemorySummary(**coach_memory.summary)
    )


@router.get('/history', response_model=ChatHistoryResponse)
def get_chat_history(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
):
    coach_memory = get_or_create_coach_memory(db, current_user.id)
    chat_memory = coach_memory.summary.get("chat", {})

    db.commit()

    return ChatHistoryResponse(
        messages=chat_memory.get("current_conversation", []),
        current_goal=chat_memory.get("current_goal"),
        preferences=chat_memory.get("preferences", []),
        topics_of_interest=chat_memory.get("topics_of_interest", []),
        progress=chat_memory.get("progress"),
    )
