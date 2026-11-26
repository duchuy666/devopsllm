from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service: str = Field(description='Observed service, or caller -> callee for a network hypothesis when evidence identifies both directed endpoints. Do not guess an edge from a route alone.')
    fault_type: Literal['Resource Exhaustion', 'Network Delay / Packet Loss', 'Pod Failure', 'Unknown']
    root_cause: str
    evidence_ids: list[str]
    rationale: str = Field(description='Brief explanation grounded in the cited observations; do not expose internal reasoning.')


class IncidentReport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    incident_id: str
    status: Literal['hypotheses_available', 'insufficient_evidence']
    hypotheses: list[Hypothesis] = Field(max_length=3)
    recommended_actions: list[str]
    missing_evidence: list[str]
    confidence: float = Field(ge=0, le=1, description='Uncalibrated model estimate, for reference only.')
