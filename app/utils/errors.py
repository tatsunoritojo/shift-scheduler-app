"""Standardized error handling — JSON for APIs, HTML for user-facing pages."""

from flask import jsonify, make_response, request
from markupsafe import escape


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


def wants_json():
    """Return True if the request is for an API path or explicitly accepts JSON."""
    if request.path.startswith('/api/'):
        return True
    accept = request.accept_mimetypes
    return accept.best_match(['application/json', 'text/html']) == 'application/json'


def render_error_page(title, message, back_url='/login', back_label='ログイン画面に戻る',
                      status=400, detail=None):
    """Render a user-friendly HTML error page with a recovery action.

    Use in page-rendering routes where a raw JSON error would leave the user
    stranded. API routes (/api/*) should continue using ``error_response``.
    """
    title_s = escape(title)
    message_s = escape(message)
    back_url_s = escape(back_url)
    back_label_s = escape(back_label)
    detail_html = f'<p class="detail">{escape(detail)}</p>' if detail else ''

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title_s} - シフリー</title>
<style>
body {{ margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
       padding: 24px; background: #f8fafc; font-family: -apple-system, BlinkMacSystemFont,
       'Segoe UI', sans-serif; }}
.card {{ background: #fff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08);
         padding: 40px 28px 32px; max-width: 420px; width: 100%; text-align: center; }}
.icon {{ width: 56px; height: 56px; border-radius: 50%; background: #fef2f2; color: #ef4444;
         display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;
         font-size: 1.8rem; font-weight: 700; }}
h1 {{ font-size: 1.2rem; color: #1e293b; margin: 0 0 12px; }}
p {{ color: #475569; line-height: 1.6; margin: 0 0 8px; font-size: 0.94rem; }}
.detail {{ color: #94a3b8; font-size: 0.82rem; margin-top: 12px; }}
.btn {{ display: inline-block; margin-top: 24px; padding: 12px 28px; background: #3b82f6;
        color: #fff; border-radius: 10px; text-decoration: none; font-weight: 600;
        font-size: 0.95rem; }}
.btn:active {{ background: #2563eb; }}
</style>
</head>
<body>
<div class="card">
<div class="icon">!</div>
<h1>{title_s}</h1>
<p>{message_s}</p>
{detail_html}
<a href="{back_url_s}" class="btn">{back_label_s}</a>
</div>
</body>
</html>"""
    response = make_response(html, status)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response
