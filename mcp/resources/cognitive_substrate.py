"""
Pydantic models for the Ultimate Cognitive Substrate Schema.
Enables runtime validation and structured reasoning evaluation.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


# ── Primary Cognitive Foundations ──────────────────────────────────────

class PremiseValidation(BaseModel):
    unstated_assumptions: List[str] = Field(default_factory=list)
    premise_veracity_evaluation: str = ""

class StateEstimation(BaseModel):
    active_goal: str = ""
    known_constraints: List[str] = Field(default_factory=list)
    system_state_hash: str = ""

class AdversarialFalsification(BaseModel):
    initial_thesis_propose: str = ""
    malicious_compliance_attack: List[str] = Field(default_factory=list)
    hardened_synthesis: str = ""

class Pathway(BaseModel):
    path_id: str
    confidence_score: float = 0.0
    complexity_risk: str = "Medium"

class DepthFirstBranching(BaseModel):
    pathways_generated: List[Pathway] = Field(default_factory=list)
    selected_execution_vector: str = ""

class EpistemicHumilityMap(BaseModel):
    established_facts: List[str] = Field(default_factory=list)
    working_inferences: List[str] = Field(default_factory=list)
    speculative_assumptions: List[str] = Field(default_factory=list)

class OpportunityCostCalculation(BaseModel):
    heavy_architectural_footprint: str = ""
    minimalist_alternative_pathway: str = ""

class InversionPrincipleAnalysis(BaseModel):
    simulated_catastrophic_failure: str = ""
    defensive_preemptive_mitigations: List[str] = Field(default_factory=list)

class SemanticCompressionTranslation(BaseModel):
    feynman_analogy_test: str = ""
    structural_purity_verification: str = ""

class PrimaryCognitiveFoundations(BaseModel):
    premise_validation: PremiseValidation = Field(default_factory=PremiseValidation)
    state_estimation: StateEstimation = Field(default_factory=StateEstimation)
    adversarial_falsification: AdversarialFalsification = Field(default_factory=AdversarialFalsification)
    depth_first_branching: DepthFirstBranching = Field(default_factory=DepthFirstBranching)
    epistemic_humility_map: EpistemicHumilityMap = Field(default_factory=EpistemicHumilityMap)
    opportunity_cost_calculation: OpportunityCostCalculation = Field(default_factory=OpportunityCostCalculation)
    inversion_principle_analysis: InversionPrincipleAnalysis = Field(default_factory=InversionPrincipleAnalysis)
    semantic_compression_translation: SemanticCompressionTranslation = Field(default_factory=SemanticCompressionTranslation)


# ── Metacognition & Processing ─────────────────────────────────────────

class ExplanatoryDepthMap(BaseModel):
    surface_intent: str = ""
    underlying_cs_primitives: List[str] = Field(default_factory=list)

class CognitiveDissonanceAudit(BaseModel):
    conflicting_constraints: List[str] = Field(default_factory=list)
    resolution_protocol: str = ""

class DialecticalInquiry(BaseModel):
    socratic_self_critique: List[str] = Field(default_factory=list)
    rebuttal_and_adaptation: str = ""

class PrematureConvergenceBrake(BaseModel):
    instinctive_first_choice_discarded: str = ""
    orthogonal_alternatives: List[str] = Field(default_factory=list)

class SemanticDriftSentinel(BaseModel):
    root_goal_alignment: str = ""
    drift_percentage: float = 0.0

class MetacognitionAndProcessing(BaseModel):
    explanatory_depth_map: ExplanatoryDepthMap = Field(default_factory=ExplanatoryDepthMap)
    cognitive_dissonance_audit: CognitiveDissonanceAudit = Field(default_factory=CognitiveDissonanceAudit)
    dialectical_inquiry: DialecticalInquiry = Field(default_factory=DialecticalInquiry)
    premature_convergence_brake: PrematureConvergenceBrake = Field(default_factory=PrematureConvergenceBrake)
    semantic_drift_sentinel: SemanticDriftSentinel = Field(default_factory=SemanticDriftSentinel)


# ── Defensive Engineering ──────────────────────────────────────────────

class IdempotencySideEffectAudit(BaseModel):
    blast_radius: List[str] = Field(default_factory=list)
    safe_to_re_run_proof: str = ""

class GracefulDegradationPlanning(BaseModel):
    primary_failure_triggers: List[str] = Field(default_factory=list)
    low_power_fallback: str = ""

class BoundaryStressTesting(BaseModel):
    null_zero_max_inputs: str = ""

class ZeroTrustSecurityReview(BaseModel):
    assumed_malicious_exploit: str = ""
    mitigation_shield: str = ""

class StateInvariantEnforcement(BaseModel):
    immutable_rule: str = ""
    validation_step: str = ""

class DefensiveEngineering(BaseModel):
    idempotency_side_effect_audit: IdempotencySideEffectAudit = Field(default_factory=IdempotencySideEffectAudit)
    graceful_degradation_planning: GracefulDegradationPlanning = Field(default_factory=GracefulDegradationPlanning)
    boundary_stress_testing: BoundaryStressTesting = Field(default_factory=BoundaryStressTesting)
    zero_trust_security_review: ZeroTrustSecurityReview = Field(default_factory=ZeroTrustSecurityReview)
    state_invariant_enforcement: StateInvariantEnforcement = Field(default_factory=StateInvariantEnforcement)


# ── Resource Management ────────────────────────────────────────────────

class ComplexityCostAnalysis(BaseModel):
    big_o_notation: str = ""
    scalability_bottleneck: str = ""

class LazyEvaluationModeling(BaseModel):
    deferred_computations: List[str] = Field(default_factory=list)

class DependencyMinimizationRouting(BaseModel):
    external_requirements: List[str] = Field(default_factory=list)
    vanilla_fallback_efficiency: str = ""

class ExecutionBottleneckPrediction(BaseModel):
    highest_latency_line: str = ""
    optimization_refactor: str = ""

class ContextWindowBudgeting(BaseModel):
    input_token_weight: str = "Medium"
    compression_strategy: str = ""

class ResourceManagement(BaseModel):
    complexity_cost_analysis: ComplexityCostAnalysis = Field(default_factory=ComplexityCostAnalysis)
    lazy_evaluation_modeling: LazyEvaluationModeling = Field(default_factory=LazyEvaluationModeling)
    dependency_minimization_routing: DependencyMinimizationRouting = Field(default_factory=DependencyMinimizationRouting)
    execution_bottleneck_prediction: ExecutionBottleneckPrediction = Field(default_factory=ExecutionBottleneckPrediction)
    context_window_budgeting: ContextWindowBudgeting = Field(default_factory=ContextWindowBudgeting)


# ── Human Utility ──────────────────────────────────────────────────────

class CognitiveLoadMinimization(BaseModel):
    ten_second_review_summary: str = ""

class ProgressiveDisclosureFormatting(BaseModel):
    executive_summary: str = ""
    hidden_implementation_details: str = ""

class IdiomaticPurityEnforcement(BaseModel):
    target_style_guide: str = ""
    anti_patterns_evaded: List[str] = Field(default_factory=list)

class PremiseCorrectionLoop(BaseModel):
    user_instruction_flaws: List[str] = Field(default_factory=list)
    proposed_course_correction: str = ""

class IntentAlignmentVerification(BaseModel):
    final_checklist: List[str] = Field(default_factory=list)

class HumanUtility(BaseModel):
    cognitive_load_minimization: CognitiveLoadMinimization = Field(default_factory=CognitiveLoadMinimization)
    progressive_disclosure_formatting: ProgressiveDisclosureFormatting = Field(default_factory=ProgressiveDisclosureFormatting)
    idiomatic_purity_enforcement: IdiomaticPurityEnforcement = Field(default_factory=IdiomaticPurityEnforcement)
    premise_correction_loop: PremiseCorrectionLoop = Field(default_factory=PremiseCorrectionLoop)
    intent_alignment_verification: IntentAlignmentVerification = Field(default_factory=IntentAlignmentVerification)


# ── Root Schema ────────────────────────────────────────────────────────

class CognitiveSubstrateSchema(BaseModel):
    """Complete 28-paradigm cognitive substrate for mem20."""
    primary_cognitive_foundations: PrimaryCognitiveFoundations = Field(default_factory=PrimaryCognitiveFoundations)
    metacognition_and_processing: MetacognitionAndProcessing = Field(default_factory=MetacognitionAndProcessing)
    defensive_engineering: DefensiveEngineering = Field(default_factory=DefensiveEngineering)
    resource_management: ResourceManagement = Field(default_factory=ResourceManagement)
    human_utility: HumanUtility = Field(default_factory=HumanUtility)

    def get_paradigm(self, paradigm_id: str) -> Optional[BaseModel]:
        """Get a specific paradigm by ID (e.g., '1_premise_validation')."""
        for field_name, field_value in self.primary_cognitive_foundations.dict().items():
            if field_name == paradigm_id:
                return field_value
        for field_name, field_value in self.metacognition_and_processing.dict().items():
            if field_name == paradigm_id:
                return field_value
        for field_name, field_value in self.defensive_engineering.dict().items():
            if field_name == paradigm_id:
                return field_value
        for field_name, field_value in self.resource_management.dict().items():
            if field_name == paradigm_id:
                return field_value
        for field_name, field_value in self.human_utility.dict().items():
            if field_name == paradigm_id:
                return field_value
        return None

    def evaluate_branch(self, paradigm_id: str, branch_data: Dict[str, Any]) -> Dict[str, Any]:
        """Score and evaluate a ToT branch against a specific paradigm."""
        paradigm = self.get_paradigm(paradigm_id)
        if not paradigm:
            return {"error": f"Unknown paradigm: {paradigm_id}"}
        
        # Score based on paradigm-specific criteria
        scores = {}
        for key, value in branch_data.items():
            if isinstance(value, (int, float)):
                scores[key] = value
            elif isinstance(value, str) and len(value) > 10:
                scores[key] = min(10, len(value) / 50)  # Simple heuristic
            elif isinstance(value, list):
                scores[key] = min(10, len(value) * 2)
            else:
                scores[key] = 5.0
        
        total = sum(scores.values()) / max(len(scores), 1)
        return {
            "paradigm": paradigm_id,
            "scores": scores,
            "total_score": round(total, 2),
            "recommendation": "accept" if total >= 7 else "prune" if total < 4 else "mutate"
        }
