from functools import wraps
from flask import session, jsonify, current_app
from app.extensions import db
from app.models.user import User
from app.utils.errors import error_response


def require_auth(f):
    """Require authenticated user in session."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return error_response("Authentication required", 401, code="AUTH_REQUIRED")
        user = db.session.get(User, user_id)
        if not user or not user.is_active:
            return error_response("User not found or inactive", 401, code="AUTH_REQUIRED")
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    """Require user to have one of the specified roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                return error_response("Authentication required", 401, code="AUTH_REQUIRED")
            user = db.session.get(User, user_id)
            if not user or not user.is_active:
                return error_response("User not found or inactive", 401, code="AUTH_REQUIRED")
            if user.role not in roles:
                return error_response("Insufficient permissions", 403, code="FORBIDDEN")
            return f(*args, **kwargs)
        return decorated
    return decorator


def get_current_user():
    """Get the current authenticated user from session."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)
