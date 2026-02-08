"""Rubric Loader for configurable decision criteria.

Loads and parses decision rubrics from markdown files,
following Anthropic's pattern of separating decision logic from execution.
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from backend.config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CriterionRule:
    """A single criterion rule from the rubric."""
    name: str
    weight: str  # high, medium, low
    evidence_required: str
    category: str


@dataclass
class StatusMapping:
    """Mapping from AI assessment to coverage status."""
    assessment: str
    maps_to: str
    action: str


@dataclass
class ThresholdRule:
    """Approval likelihood threshold rule."""
    min_likelihood: float
    max_likelihood: float
    status: str
    recommendation: str


@dataclass
class GapPriorityRule:
    """Documentation gap priority rule."""
    gap_type: str
    priority: str
    impact: str


@dataclass
class DecisionRubric:
    """Complete parsed decision rubric."""
    version: str = "1.0"

    # Decision authority
    ai_can_approve: bool = True
    ai_can_pend: bool = True
    ai_can_deny: bool = False  # Always False per conservative model

    # Status mappings
    status_mappings: List[StatusMapping] = field(default_factory=list)

    # Threshold rules
    threshold_rules: List[ThresholdRule] = field(default_factory=list)

    # Criteria by category
    diagnosis_criteria: List[CriterionRule] = field(default_factory=list)
    step_therapy_criteria: List[CriterionRule] = field(default_factory=list)
    clinical_criteria: List[CriterionRule] = field(default_factory=list)
    documentation_criteria: List[CriterionRule] = field(default_factory=list)

    # Gap rules
    gap_priority_rules: List[GapPriorityRule] = field(default_factory=list)

    # Conservative decision rules
    conservative_rules: List[str] = field(default_factory=list)

    # Raw markdown content
    raw_content: str = ""

    def get_all_criteria(self) -> List[CriterionRule]:
        """Get all criteria across categories."""
        return (
            self.diagnosis_criteria +
            self.step_therapy_criteria +
            self.clinical_criteria +
            self.documentation_criteria
        )

    def get_threshold_for_likelihood(self, likelihood: float) -> Optional[ThresholdRule]:
        """Get the threshold rule matching a likelihood score."""
        for rule in self.threshold_rules:
            if rule.min_likelihood <= likelihood <= rule.max_likelihood:
                return rule
        return None

    def requires_human_review(self, likelihood: float) -> bool:
        """Check if likelihood requires human review."""
        return likelihood < 0.4

    def to_prompt_context(self) -> str:
        """Convert rubric to context string for LLM prompts."""
        sections = []

        # Decision authority
        sections.append("## Decision Authority")
        sections.append("- AI can recommend: APPROVE, PEND")
        sections.append("- AI CANNOT recommend: DENY (human decision required)")
        sections.append("")

        # Thresholds
        sections.append("## Approval Likelihood Thresholds")
        for rule in self.threshold_rules:
            sections.append(
                f"- {rule.min_likelihood*100:.0f}%-{rule.max_likelihood*100:.0f}%: "
                f"{rule.status} -> {rule.recommendation}"
            )
        sections.append("")

        # Criteria summary
        sections.append("## Criteria Categories")
        sections.append(f"- Diagnosis criteria: {len(self.diagnosis_criteria)} rules")
        sections.append(f"- Step therapy criteria: {len(self.step_therapy_criteria)} rules")
        sections.append(f"- Clinical criteria: {len(self.clinical_criteria)} rules")
        sections.append(f"- Documentation criteria: {len(self.documentation_criteria)} rules")
        sections.append("")

        # Conservative rules
        sections.append("## Conservative Decision Rules")
        for i, rule in enumerate(self.conservative_rules, 1):
            sections.append(f"{i}. {rule}")

        return "\n".join(sections)


class RubricLoader:
    """
    Loads and parses decision rubrics from markdown files.

    Rubrics define the decision criteria and rules that the AI
    uses for coverage assessment. This separates logic from execution.
    """

    def __init__(self, rubrics_dir: Optional[Path] = None):
        """
        Initialize the rubric loader.

        Args:
            rubrics_dir: Directory containing rubric markdown files
        """
        self.rubrics_dir = rubrics_dir or Path("data/rubrics")
        self._cache: Dict[str, DecisionRubric] = {}
        logger.info("Rubric loader initialized", rubrics_dir=str(self.rubrics_dir))

    def load(self, payer_name: Optional[str] = None) -> DecisionRubric:
        """
        Load a rubric for a payer.

        Args:
            payer_name: Optional payer name for payer-specific rubric

        Returns:
            Parsed DecisionRubric
        """
        # Check cache
        cache_key = payer_name or "default"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Try payer-specific rubric first
        rubric_path = None
        rubrics_root = self.rubrics_dir.resolve()
        if payer_name:
            payer_key = payer_name.lower().replace(" ", "_")
            payer_path = (self.rubrics_dir / f"{payer_key}_rubric.md").resolve()
            # Path traversal protection
            try:
                payer_path.relative_to(rubrics_root)
            except ValueError:
                logger.warning(
                    "Rubric path traversal blocked",
                    payer_name=payer_name,
                    resolved_path=str(payer_path),
                )
                raise ValueError(f"Invalid rubric path for payer: {payer_name}")
            if payer_path.exists():
                rubric_path = payer_path

        # Fall back to default
        if not rubric_path:
            rubric_path = self.rubrics_dir / "default_rubric.md"

        if not rubric_path.exists():
            logger.warning(
                "Rubric not found, using built-in defaults",
                path=str(rubric_path)
            )
            return self._get_builtin_defaults()

        # Load and parse
        rubric = self._parse_rubric(rubric_path)
        self._cache[cache_key] = rubric

        logger.info(
            "Rubric loaded",
            payer=payer_name or "default",
            path=str(rubric_path),
            criteria_count=len(rubric.get_all_criteria())
        )

        return rubric

    def _parse_rubric(self, path: Path) -> DecisionRubric:
        """Parse a rubric markdown file into a DecisionRubric."""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        rubric = DecisionRubric(raw_content=content)

        # Parse threshold rules from table
        rubric.threshold_rules = self._parse_threshold_table(content)

        # Parse criteria tables
        rubric.diagnosis_criteria = self._parse_criteria_table(content, "Diagnosis Criteria")
        rubric.step_therapy_criteria = self._parse_criteria_table(content, "Step Therapy Criteria")
        rubric.clinical_criteria = self._parse_criteria_table(content, "Clinical Criteria")
        rubric.documentation_criteria = self._parse_criteria_table(content, "Documentation Criteria")

        # Parse gap priority rules
        rubric.gap_priority_rules = self._parse_gap_rules(content)

        # Parse status mappings
        rubric.status_mappings = self._parse_status_mappings(content)

        # Parse conservative rules
        rubric.conservative_rules = self._parse_conservative_rules(content)

        return rubric

    def _parse_threshold_table(self, content: str) -> List[ThresholdRule]:
        """Parse approval likelihood threshold table."""
        rules = []

        # Find the threshold section
        pattern = r"## Approval Likelihood Thresholds\n\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)"
        match = re.search(pattern, content)

        if match:
            rows = match.group(1).strip().split("\n")
            for row in rows:
                cols = [c.strip() for c in row.split("|")[1:-1]]
                if len(cols) >= 4:
                    # Parse range like "80% - 100%"
                    range_match = re.search(r"(\d+)%?\s*-\s*(\d+)%?", cols[0])
                    if range_match:
                        rules.append(ThresholdRule(
                            min_likelihood=float(range_match.group(1)) / 100,
                            max_likelihood=float(range_match.group(2)) / 100,
                            status=cols[1],
                            recommendation=cols[2]
                        ))

        # Add defaults if parsing failed
        if not rules:
            logger.warning(
                "Failed to parse threshold table from rubric, using defaults"
            )
            rules = [
                ThresholdRule(0.80, 1.00, "High confidence", "APPROVE"),
                ThresholdRule(0.60, 0.79, "Moderate confidence", "APPROVE"),
                ThresholdRule(0.40, 0.59, "Borderline", "PEND"),
                ThresholdRule(0.20, 0.39, "Low confidence", "REQUIRES_HUMAN_REVIEW"),
                ThresholdRule(0.00, 0.19, "Very low", "REQUIRES_HUMAN_REVIEW"),
            ]

        return rules

    def _parse_criteria_table(self, content: str, section_name: str) -> List[CriterionRule]:
        """Parse a criteria table from the rubric."""
        criteria = []

        # Find section
        pattern = rf"### \d+\. {section_name}\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)"
        match = re.search(pattern, content)

        if match:
            rows = match.group(1).strip().split("\n")
            for row in rows:
                cols = [c.strip() for c in row.split("|")[1:-1]]
                if len(cols) >= 3:
                    criteria.append(CriterionRule(
                        name=cols[0],
                        weight=cols[1].lower(),
                        evidence_required=cols[2],
                        category=section_name
                    ))

        return criteria

    def _parse_gap_rules(self, content: str) -> List[GapPriorityRule]:
        """Parse gap priority rules."""
        rules = []

        pattern = r"## Gap Priority Rules\n\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)"
        match = re.search(pattern, content)

        if match:
            rows = match.group(1).strip().split("\n")
            for row in rows:
                cols = [c.strip() for c in row.split("|")[1:-1]]
                if len(cols) >= 3:
                    rules.append(GapPriorityRule(
                        gap_type=cols[0],
                        priority=cols[1].lower(),
                        impact=cols[2]
                    ))

        return rules

    def _parse_status_mappings(self, content: str) -> List[StatusMapping]:
        """Parse coverage status mappings."""
        mappings = []

        pattern = r"## Coverage Status Mappings\n\n\|.*?\n\|[-\s|]+\n((?:\|.*?\n)+)"
        match = re.search(pattern, content)

        if match:
            rows = match.group(1).strip().split("\n")
            for row in rows:
                cols = [c.strip() for c in row.split("|")[1:-1]]
                if len(cols) >= 3:
                    mappings.append(StatusMapping(
                        assessment=cols[0],
                        maps_to=cols[1].strip("`"),
                        action=cols[2]
                    ))

        return mappings

    def _parse_conservative_rules(self, content: str) -> List[str]:
        """Parse conservative decision rules."""
        rules = []

        # Find rule sections
        rule_pattern = r"### Rule \d+: ([^\n]+)\n(.*?)(?=### Rule|\Z)"
        matches = re.findall(rule_pattern, content, re.DOTALL)

        for title, _ in matches:
            rules.append(title)

        # Default rules if parsing failed
        if not rules:
            logger.warning(
                "Failed to parse conservative rules from rubric, using defaults"
            )
            rules = [
                "Never Auto-Deny - AI must NEVER output a denial recommendation",
                "Document All Reasoning - Every assessment must include full evidence",
                "Err on Side of Documentation - When uncertain, request more documentation",
                "Human Gate Enforcement - Low confidence cases must pause for human review"
            ]

        return rules

    def _get_builtin_defaults(self) -> DecisionRubric:
        """Get built-in default rubric when no file is available."""
        return DecisionRubric(
            version="1.0-builtin",
            ai_can_approve=True,
            ai_can_pend=True,
            ai_can_deny=False,
            threshold_rules=[
                ThresholdRule(0.80, 1.00, "High confidence", "APPROVE"),
                ThresholdRule(0.60, 0.79, "Moderate confidence", "APPROVE"),
                ThresholdRule(0.40, 0.59, "Borderline", "PEND"),
                ThresholdRule(0.20, 0.39, "Low confidence", "REQUIRES_HUMAN_REVIEW"),
                ThresholdRule(0.00, 0.19, "Very low", "REQUIRES_HUMAN_REVIEW"),
            ],
            conservative_rules=[
                "Never Auto-Deny",
                "Document All Reasoning",
                "Err on Side of Documentation",
                "Human Gate Enforcement"
            ]
        )

    def clear_cache(self) -> None:
        """Clear the rubric cache."""
        self._cache.clear()


# Global instance
_rubric_loader: Optional[RubricLoader] = None


def get_rubric_loader() -> RubricLoader:
    """Get or create the global rubric loader instance."""
    global _rubric_loader
    if _rubric_loader is None:
        _rubric_loader = RubricLoader()
    return _rubric_loader
