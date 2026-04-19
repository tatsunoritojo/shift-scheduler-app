"""User-Agent helpers for in-app browser (WebView) detection.

Google OAuth 2.0 blocks requests from embedded user agents (WebViews)
with `error=disallowed_useragent`. These helpers let the auth flow detect
such clients and redirect them to an intermediate page that opens the
current URL in an external browser (Safari / Chrome).
"""
import re
from urllib.parse import quote

from flask import request, redirect


_WEBVIEW_PATTERNS = [
    re.compile(r'\bLine/', re.IGNORECASE),                         # LINE
    re.compile(r'\bInstagram\b', re.IGNORECASE),                   # Instagram
    re.compile(r'\bFBAN\b|\bFBAV\b|\bFB_IAB\b|FBIOS', re.IGNORECASE),  # Facebook / Messenger
    re.compile(r'\bTwitter\b|TwitterAndroid', re.IGNORECASE),      # X (旧 Twitter)
    re.compile(r'KAKAOTALK', re.IGNORECASE),                       # KakaoTalk
    re.compile(r'MicroMessenger', re.IGNORECASE),                  # WeChat
    re.compile(r'TikTok', re.IGNORECASE),                          # TikTok
    re.compile(r'; wv\)', re.IGNORECASE),                          # Android WebView (generic)
]


def is_webview(user_agent):
    """Return True if the User-Agent looks like an in-app WebView."""
    if not user_agent:
        return False
    return any(p.search(user_agent) for p in _WEBVIEW_PATTERNS)


def detect_platform(user_agent):
    """Return 'ios', 'android', or 'other' based on the User-Agent."""
    if not user_agent:
        return 'other'
    ua = user_agent.lower()
    if 'iphone' in ua or 'ipad' in ua or 'ipod' in ua:
        return 'ios'
    if 'android' in ua:
        return 'android'
    return 'other'


def webview_redirect_if_needed():
    """Redirect in-app WebView users to the external-browser landing page.

    Shared guard used by auth / invite routes. Returns a Flask redirect
    response when the request comes from an in-app WebView, or None when
    the request should proceed normally.
    """
    if not is_webview(request.headers.get('User-Agent', '')):
        return None
    current = request.full_path.rstrip('?')
    return redirect(f'/auth/open-in-browser?next={quote(current, safe="")}')
