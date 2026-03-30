# core/exceptions.py — PLAGENOR 4.0 Custom Exceptions


class PlagenorError(Exception):
    """Base exception for all PLAGENOR errors."""
    pass


class InvalidTransitionError(PlagenorError):
    """Raised when a workflow state transition is not allowed."""
    pass


class RequestNotFoundError(PlagenorError):
    """Raised when a request cannot be found."""
    pass


class MissingTransitionDataError(PlagenorError):
    """Raised when required data for a transition is missing."""
    pass


class WorkflowError(PlagenorError):
    """Generic workflow engine error."""
    pass


class BudgetExceededError(PlagenorError):
    """Raised when IBTIKAR annual budget cap would be exceeded."""
    pass


class BudgetOverrideRequiredError(PlagenorError):
    """Raised when budget is exceeded but SUPER_ADMIN override is possible."""
    pass


class NoAvailableMemberError(PlagenorError):
    """Raised when no member is available for assignment."""
    pass


class MemberUnavailableError(PlagenorError):
    """Raised when a specific member is not available."""
    pass


class MemberOverloadedError(PlagenorError):
    """Raised when a member has reached max load."""
    pass


class InvoiceLockError(PlagenorError):
    """Raised when attempting to modify a locked invoice."""
    pass


class AuthorizationError(PlagenorError):
    """Raised when a user lacks permission for an action."""
    pass


class ValidationError(PlagenorError):
    """Raised when input validation fails."""
    pass
