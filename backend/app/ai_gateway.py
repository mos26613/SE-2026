"""Centralized AI Gateway service for task classification and AI operations."""

from . import ai_filter
from .config import Settings
from .models import AIResult, TaskIn


class AIGateway:
    """Centralized gateway wrapping AI classification with safe fallback behavior."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def classify_tasks(self, tasks: list[TaskIn]) -> dict[str, AIResult]:
        if not tasks:
            return {}
        return ai_filter.classify_tasks(tasks, self.settings)


def get_ai_gateway(settings: Settings) -> AIGateway:
    return AIGateway(settings)


def classify_tasks_via_gateway(tasks: list[TaskIn], settings: Settings) -> dict[str, AIResult]:
    return get_ai_gateway(settings).classify_tasks(tasks)