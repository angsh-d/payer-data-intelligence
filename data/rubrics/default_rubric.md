# Prior Authorization Decision Rubric

This rubric defines the criteria and decision rules for coverage assessment and approval recommendations. It implements the Anthropic conservative decision model where AI never recommends denial.

## Decision Authority Matrix

| Decision Type | AI Authority | Human Required | Notes |
|--------------|--------------|----------------|-------|
| APPROVE | Yes (recommend) | Optional confirmation | AI can recommend approval when all criteria met |
| PEND | Yes (recommend) | Optional confirmation | AI can recommend pending for documentation |
| DENY | **NO** | **ALWAYS REQUIRED** | AI must NEVER recommend denial |
| OVERRIDE | No | Always | Humans can override any AI recommendation |

## Coverage Status Mappings

| AI Assessment | Maps To | Action |
|--------------|---------|--------|
| All criteria met, high confidence (>80%) | `covered` | Recommend APPROVE |
| Most criteria met, confidence 60-80% | `likely_covered` | Recommend APPROVE with PA |
| PA required by policy | `requires_pa` | Recommend PEND for PA submission |
| Conditional coverage | `conditional` | Recommend PEND with conditions |
| Missing documentation | `pend` | Recommend PEND for documentation |
| Coverage uncertain | `requires_human_review` | STOP - Human must decide |
| Policy excludes medication | `requires_human_review` | STOP - Human must decide |
| Criteria not met | `requires_human_review` | STOP - Human must decide |

## Approval Likelihood Thresholds

| Likelihood Range | Status | AI Recommendation |
|-----------------|--------|-------------------|
| 80% - 100% | High confidence | APPROVE |
| 60% - 79% | Moderate confidence | APPROVE (with PA) |
| 40% - 59% | Borderline | PEND for documentation |
| 20% - 39% | Low confidence | REQUIRES_HUMAN_REVIEW |
| 0% - 19% | Very low | REQUIRES_HUMAN_REVIEW |

## Criteria Categories

### 1. Diagnosis Criteria
| Criterion | Weight | Evidence Required |
|-----------|--------|------------------|
| Approved indication | High | ICD-10 code matching policy |
| Off-label with evidence | Medium | Published studies, guidelines |
| Clinical trial indication | Medium | Trial documentation |
| Compendia support | Medium | NCCN, AHFS listing |

### 2. Step Therapy Criteria
| Criterion | Weight | Evidence Required |
|-----------|--------|------------------|
| First-line completed | High | Prior treatment records |
| Adequate trial duration | Medium | 30-90 days depending on class |
| Documented failure/intolerance | High | Clinical notes, lab results |
| Contraindication documented | High | Allergy records, contraindications |

### 3. Clinical Criteria
| Criterion | Weight | Evidence Required |
|-----------|--------|------------------|
| Disease severity documented | High | Labs, imaging, clinical notes |
| Prior treatment history | Medium | Treatment records |
| Lab values in range | High | Recent lab results |
| Specialist consultation | Low-Medium | Referral notes |

### 4. Documentation Criteria
| Criterion | Weight | Evidence Required |
|-----------|--------|------------------|
| Valid prescription | Required | Current prescription |
| Provider credentials | Required | Valid NPI, appropriate specialty |
| Patient eligibility | Required | Active insurance coverage |
| Clinical rationale | High | Letter of medical necessity |

## Gap Priority Rules

| Gap Type | Priority | Impact on Decision |
|----------|----------|-------------------|
| Missing required documentation | High | PEND |
| Missing clinical rationale | High | PEND |
| Step therapy not documented | Medium | PEND (may approve with override) |
| Lab results outdated | Medium | PEND for current labs |
| Specialist note missing | Low | May approve without |

## Payer-Specific Overrides

Payer-specific criteria can override default rubric rules. Load payer rubrics from:
- `data/rubrics/cigna_rubric.md`
- `data/rubrics/uhc_rubric.md`
- `data/rubrics/{payer}_rubric.md`

If no payer-specific rubric exists, use this default rubric.

## Conservative Decision Rules

### Rule 1: Never Auto-Deny
AI must NEVER output a denial recommendation. If coverage appears unlikely:
1. Map to `requires_human_review`
2. Document all concerns clearly
3. Present evidence to human reviewer
4. Human makes final denial decision

### Rule 2: Document All Reasoning
Every assessment must include:
- Criteria evaluated with pass/fail status
- Evidence supporting each criterion
- Gaps identified with suggested resolution
- Confidence score with explanation
- Explicit statement if human review required

### Rule 3: Err on Side of Documentation
When uncertain:
- Request additional documentation (PEND)
- Do not conclude non-coverage
- Allow human to make coverage determination

### Rule 4: Human Gate Enforcement
Cases with these conditions MUST pause for human review:
- Coverage status is `requires_human_review`
- Approval likelihood < 40%
- Any criterion flagged as potential denial
- Override of previous AI recommendation
- Escalation requested

## Confidence Calibration

| Confidence Level | Interpretation | Expected Accuracy |
|-----------------|----------------|-------------------|
| 90-100% | Very high | 95%+ correct predictions |
| 70-89% | High | 85-95% correct predictions |
| 50-69% | Moderate | 70-85% correct predictions |
| 30-49% | Low | 50-70% correct predictions |
| 0-29% | Very low | Human review required |

## Output Format Requirements

Assessment output must include:
```json
{
  "coverage_status": "covered|likely_covered|requires_pa|conditional|pend|requires_human_review",
  "approval_likelihood": 0.0-1.0,
  "criteria_assessments": [...],
  "documentation_gaps": [...],
  "recommendations": [...],
  "requires_human_review": true|false,
  "human_review_reason": "explanation if human review required"
}
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial rubric based on Anthropic skill pattern |
