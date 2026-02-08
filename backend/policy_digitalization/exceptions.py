"""Exceptions for the policy digitalization module."""


class ExtractionError(Exception):
    """Error during policy extraction (Pass 1)."""
    pass


class ValidationError(Exception):
    """Error during extraction validation (Pass 2)."""
    pass


class EvaluationError(Exception):
    """Error during deterministic criteria evaluation."""
    pass


class PolicyNotFoundError(Exception):
    """Requested policy not found in repository."""
    pass
