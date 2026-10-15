from pydantic import BaseModel, Field
from typing import Literal

SupportTiming = Literal["before_run", "after_run", "separate", "rest_day"]

class RunningBlock(BaseModel):
    type: str
    distance_km: float = Field(gt=0)
    intensity_level: Literal[
        "recovery",
        "very_easy",
        "easy",
        "steady",
        "tempo",
        "threshold",
        "interval",
        "race",
    ]
    details: str


class SupportBlock(BaseModel):
    focus: str
    timing: SupportTiming
    duration_minutes: int
    details: str


class WalkingBlock(BaseModel):
    type: Literal["walk", "walk_run"]
    distance_km: float = Field(gt=0)
    duration_minutes: int = Field(ge=1)
    intensity_level: Literal[
        "gentle",
        "very_easy",
        "comfortable",
        "easy",
        "brisk",
    ]
    details: str


class TrainingDay(BaseModel):
    week_number: int = Field(ge=1)
    date: str
    day: str
    running: RunningBlock | None = None
    walking: WalkingBlock | None = None
    strength: SupportBlock | None = None
    mobility: SupportBlock | None = None
    notes: str | None = None


class WeeklyDistance(BaseModel):
    week_number: int = Field(ge=1)
    start_date: str
    end_date: str
    distance_km: float


class PlanContent(BaseModel):
    summary: str
    weekly_distance: list[WeeklyDistance]
    training_days: list[TrainingDay]
    safety_notes: list[str]


class PlanExplanation(BaseModel):
    why_this_plan_fits: list[str]


class RunningPlanOutput(BaseModel):
    content: PlanContent
    explanation: PlanExplanation


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RunnerMemory(BaseModel):
    current_goal: str | None = None
    preferences: list[str] = Field(default_factory=list)
    topics_of_interest: list[str] = Field(default_factory=list)
    progress: str | None = None


class AgreedActionOutput(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    runner_quote: str = Field(min_length=1, max_length=1000)


class MemoryEvidence(BaseModel):
    field: Literal["current_goal", "preferences", "topics_of_interest", "progress"]
    runner_quote: str = Field(min_length=1, max_length=1000)
    operation: Literal["add", "replace", "clear"]


class ChatSummaryOutput(RunnerMemory):
    recap: str = Field(default="", max_length=3000)
    next_steps: list[AgreedActionOutput] = Field(default_factory=list, max_length=10)
    open_questions: list[str] = Field(default_factory=list, max_length=10)
    memory_evidence: list[MemoryEvidence] = Field(default_factory=list, max_length=30)


class SavedNextStep(AgreedActionOutput):
    id: str
    completed: bool = False


class MemoryChange(BaseModel):
    field: str
    before: str | list[str] | None
    after: str | list[str] | None
    runner_quote: str | None = None


class CompletedChatSession(BaseModel):
    id: str
    started_at: str | None = None
    ended_at: str
    recap: str
    next_steps: list[SavedNextStep] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    memory_changes: list[MemoryChange] = Field(default_factory=list)


class ChatMemory(RunnerMemory):
    current_conversation: list[ChatMessage] = Field(
        default_factory=list
    )
    active_session_id: str | None = None
    started_at: str | None = None
    session_history: list[CompletedChatSession] = Field(default_factory=list)
    revision: int = 0


class CoachMemorySummary(BaseModel):
    chat: ChatMemory = Field(default_factory=ChatMemory)


class ChatReplyOutput(BaseModel):
    reply: str
