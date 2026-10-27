class ApiError(Exception):
    """An error the API returns to the caller as JSON with an HTTP status."""

    def __init__(self, status, code, message, **details):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def bad_request(message, **details):
    return ApiError(400, "BAD_REQUEST", message, **details)


def not_found(message="Not found"):
    return ApiError(404, "NOT_FOUND", message)


def forbidden(message="You are not allowed to do that"):
    return ApiError(403, "FORBIDDEN", message)


def conflict(message, **details):
    return ApiError(409, "CONFLICT", message, **details)
