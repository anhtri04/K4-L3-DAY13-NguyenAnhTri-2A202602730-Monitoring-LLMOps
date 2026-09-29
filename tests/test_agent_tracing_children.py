from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class FakeManagedPrompt:
    version = 1

    def compile(self, **variables: str) -> str:
        return f"Feature={variables['feature']}\nQuestion={variables['message']}"


class FakeObservation:
    def __init__(self, name: str, as_type: str, kwargs: dict) -> None:
        self.name = name
        self.as_type = as_type
        self.kwargs = kwargs
        self.updates: list[dict] = []

    def update(self, **kwargs) -> "FakeObservation":
        self.updates.append(kwargs)
        return self


class RecordingObservationClient:
    def __init__(self) -> None:
        self.prompt = FakeManagedPrompt()
        self.span_updates: list[dict] = []
        self.observations: list[FakeObservation] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, name: str, as_type: str = "span", **kwargs):
        observation = FakeObservation(name, as_type, kwargs)
        self.observations.append(observation)
        yield observation


def test_agent_instruments_retriever_and_generation_children(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingObservationClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    @contextmanager
    def record_attributes(**kwargs):
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="refund policy",
        correlation_id="req-12345678",
    )

    by_type = {observation.as_type: observation for observation in client.observations}
    assert set(by_type) == {"retriever", "generation"}

    retriever = by_type["retriever"]
    assert retriever.updates[-1]["output"]["doc_count"] == 1

    generation = by_type["generation"]
    assert generation.kwargs["model"] == agent.model
    assert generation.kwargs["prompt"] is client.prompt
    generation_update = generation.updates[-1]
    assert generation_update["usage_details"]["input"] > 0
    assert generation_update["usage_details"]["output"] > 0
    assert generation_update["cost_details"]["total"] > 0
    assert generation_update["output"]["answer_preview"]
