"""Pydantic-модели запросов и ответов API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    mode: str = Field(..., pattern="^(single|double)$", description="Режим: 'single' или 'double'")
    city: str | None = Field(None, min_length=1, description="Город (для mode='single')")
    city_a: str | None = Field(None, min_length=1, description="Город A (для mode='double')")
    city_b: str | None = Field(None, min_length=1, description="Город B (для mode='double')")


class GenerateResponse(BaseModel):
    task_id: str
    status: str
    position: int | None = None


class TaskStatus(BaseModel):
    task_id: str
    status: str
    mode: str | None = None
    cities: list[str] | None = None
    progress: str | None = None
    error: str | None = None
    video_url: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class TaskListResponse(BaseModel):
    tasks: list[TaskStatus]


class QueueInfoResponse(BaseModel):
    queue_size: int
    max_queue_size: int


class ErrorResponse(BaseModel):
    error: str
