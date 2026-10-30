"""Bounded and auditable specialist workflow; never auto-select paid providers."""

from copy import deepcopy
from typing import Mapping

from nextrail_ai import PlanningRequest, select_provider

from .agents import (
    CatalogAgent, OrchestrationError, OrchestrationResult, PlanningAgent,
    QualityAgent, SkillGapAgent, StageRecord,
)


def orchestrate(catalog, request: PlanningRequest, *, env: Mapping[str, str] | None = None,
                priority_provider=None) -> OrchestrationResult:
    """Execute four fixed stages with fail-closed publication.

    A fully deterministic result is always available without provider configuration.
    Provider configuration is explicit; no automatic cloud or remote-model fallback.
    """
    if not isinstance(request, PlanningRequest):
        raise OrchestrationError("PlanningRequest required")
    try:
        stable_catalog = deepcopy(catalog)
        stages = []
        resources = CatalogAgent().run(stable_catalog)
        stages.append(StageRecord("catalog_validation", "passed"))
        missing = SkillGapAgent().run(stable_catalog, request)
        stages.append(StageRecord("skill_gap", "passed"))
        if priority_provider is None:
            config = {} if env is None else env
            runtime = config.get("NEXTRAIL_AGENT_RUNTIME", "native")
            if runtime == "native":
                priority_provider = select_provider(config)
            elif runtime == "strands_ollama":
                if config.get("NEXTRAIL_AI_PROVIDER") != "ollama":
                    raise OrchestrationError("Strands requires explicit local Ollama opt-in")
                local = select_provider(config)
                from .strands_local import StrandsOllamaPriorityProvider

                priority_provider = StrandsOllamaPriorityProvider(model=local.model)
            else:
                raise OrchestrationError("Unsupported orchestration runtime")
        pathway = PlanningAgent().run(stable_catalog, request, priority_provider)
        stages.append(StageRecord("pathway_planning", "passed"))
        quality = QualityAgent().run(stable_catalog, request, missing, pathway, resources)
        stages.append(StageRecord("quality_gate", "passed"))
        return OrchestrationResult(pathway=quality, stages=tuple(stages))
    except (OrchestrationError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise OrchestrationError("Orchestration rejected the request or catalog") from exc
