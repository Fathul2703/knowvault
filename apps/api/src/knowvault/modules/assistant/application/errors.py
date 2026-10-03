"""Client-facing errors of the assistant."""

from knowvault.core.errors import ConflictError, RateLimitedError


class AnswerInProgressError(ConflictError):
    code = "answer_in_progress"
    title = "An answer is already being written"


class TokenQuotaExceededError(RateLimitedError):
    code = "token_quota_exceeded"
    title = "Daily token quota used up"
