class ApplicationError(Exception):
    """Base error for application-level failures."""


class TopicNotFoundError(ApplicationError):
    """Raised when a topic does not exist."""


class EmptyTopicError(ApplicationError):
    """Raised when a topic has no available words."""


class InvalidSessionStateError(ApplicationError):
    """Raised when the requested session action is invalid."""


class NotEnoughOptionsError(ApplicationError):
    """Raised when a multiple choice question cannot be formed."""


class InvalidTopicLessonSelectionError(ApplicationError):
    """Raised when the selected lesson does not belong to the selected topic."""
