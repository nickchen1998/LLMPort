"""/v1 的請求格式（照 OpenAI；沒用到的欄位允許帶，但不處理）。"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workers.engines.base import MAX_OPTIONS


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | list[dict] | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    stream_options: dict | None = None
    temperature: float | None = Field(None, ge=0, le=2)
    top_p: float | None = Field(None, gt=0, le=1)
    max_tokens: int | None = Field(None, ge=1)
    max_completion_tokens: int | None = Field(None, ge=1)
    stop: str | list[str] | None = None
    seed: int | None = None
    n: int | None = Field(None, ge=1)
    tools: list[Any] | None = None
    tool_choice: Any = None
    response_format: dict | None = None


class EmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    input: str | list[str]
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: int | None = Field(None, ge=1)


class DecisionChoice(BaseModel):
    value: str | bool
    description: str | None = None


class DecisionLevel(BaseModel):
    label: str = Field(min_length=1)
    description: str | None = None


class DecisionQuestion(BaseModel):
    type: Literal["predicate", "choice", "score"]
    name: str | None = None
    instructions: str = Field(min_length=1)
    choices: list[DecisionChoice] | None = None
    levels: list[DecisionLevel] | None = None

    @model_validator(mode="after")
    def check_options(self):
        if self.type == "choice":
            if not self.choices or not 2 <= len(self.choices) <= MAX_OPTIONS:
                raise ValueError(f"choice questions need 2 to {MAX_OPTIONS} choices")
            values = [(type(c.value), c.value) for c in self.choices]
            if len(set(values)) != len(values):
                raise ValueError("choice values must be unique")
        if self.type == "score" and (not self.levels or not 2 <= len(self.levels) <= MAX_OPTIONS):
            raise ValueError(f"score questions need 2 to {MAX_OPTIONS} levels")
        return self


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    input: str | list[dict]
    questions: list[DecisionQuestion] = Field(min_length=1, max_length=200)
