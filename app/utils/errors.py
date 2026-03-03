"""Standardized API error handling."""

from flask import jsonify


class APIError(Exception):
    """Raise in any endpoint to produce a consistent JSON error response.

    Usage::

        raise APIError("Not found", 404, code="NOT_FOUND")
    """

    def __init__(self, message, status_code=400, code=None, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


def error_response(message, status_code=400, code=None, details=None):
    """Build a standardised JSON error response.

    Returns (Response, status_code) tuple suitable for returning from a view.
    """
    body = {"error": message}
    if code:
        body["code"] = code
    if details:
        body["details"] = details
    return jsonify(body), status_code
