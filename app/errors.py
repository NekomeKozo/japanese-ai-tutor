class TutorError(Exception):
    """A safe, user-facing error. Never include upstream bodies or secrets."""

    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
