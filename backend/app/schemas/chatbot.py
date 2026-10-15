from pydantic import BaseModel, Field, field_validator

from app.schemas.running_structured_outputs import ChatMessage, CoachMemorySummary, CompletedChatSession, RunnerMemory


class ChatbotRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=2000,
    )

    @field_validator("message", mode="before")
    @classmethod
    def clean_message(cls, value):
        if isinstance(value, str):
            return value.strip()

        return value


class ChatbotResponse(BaseModel):
    reply: str
    active_session_id: str | None = None
    revision: int = 0


class EndChatRequest(BaseModel):
    session_id: str | None = None


class MemoryUpdateRequest(RunnerMemory):
    revision: int = Field(ge=0)

    @field_validator("current_goal", "progress")
    @classmethod
    def bounded_text(cls, value):
        if value is not None and len(value) > 2000:
            raise ValueError("Keep each memory field under 2000 characters.")
        return value.strip() or None if value is not None else None

    @field_validator("preferences", "topics_of_interest")
    @classmethod
    def bounded_list(cls, values):
        if len(values) > 30 or any(len(value) > 500 for value in values):
            raise ValueError("Use at most 30 entries of 500 characters each.")
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class NextStepUpdateRequest(BaseModel):
    completed: bool
    revision: int = Field(ge=0)


class ChatbotEndResponse(BaseModel):
    summary: CoachMemorySummary
    session: CompletedChatSession | None = None


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessage] = Field(
        default_factory=list,
    )
    current_goal: str | None = None
    preferences: list[str] = Field(
        default_factory=list,
    )
    topics_of_interest: list[str] = Field(
        default_factory=list,
    )
    progress: str | None = None
    active_session_id: str | None = None
    session_history: list[CompletedChatSession] = Field(default_factory=list)
    revision: int = 0
