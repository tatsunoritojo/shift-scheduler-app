"""Tests for User-Agent detection and WebView guard helpers."""

from app.utils.useragent import is_webview, detect_platform


LINE_IOS_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Line/13.11.0'
)
LINE_ANDROID_UA = (
    'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36 Line/13.11.0'
)
INSTAGRAM_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
    'AppleWebKit/605.1.15 Instagram 305.0.0.34.111'
)
FACEBOOK_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
    'AppleWebKit/605.1.15 [FBAN/FBIOS;FBAV/450.0]'
)
TWITTER_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 '
    'Twitter for iPhone'
)
ANDROID_WEBVIEW_UA = (
    'Mozilla/5.0 (Linux; Android 10; SM-G975F; wv) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Version/4.0 Chrome/90.0.4430.91 Mobile Safari/537.36'
)
SAFARI_IOS_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
)
CHROME_ANDROID_UA = (
    'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36'
)
CHROME_DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36'
)


class TestIsWebview:
    """WebView detection must cover the major in-app browsers."""

    def test_line_ios(self):
        assert is_webview(LINE_IOS_UA) is True

    def test_line_android(self):
        assert is_webview(LINE_ANDROID_UA) is True

    def test_instagram(self):
        assert is_webview(INSTAGRAM_UA) is True

    def test_facebook(self):
        assert is_webview(FACEBOOK_UA) is True

    def test_twitter(self):
        assert is_webview(TWITTER_UA) is True

    def test_generic_android_webview(self):
        assert is_webview(ANDROID_WEBVIEW_UA) is True

    def test_safari_is_not_webview(self):
        assert is_webview(SAFARI_IOS_UA) is False

    def test_chrome_mobile_is_not_webview(self):
        assert is_webview(CHROME_ANDROID_UA) is False

    def test_chrome_desktop_is_not_webview(self):
        assert is_webview(CHROME_DESKTOP_UA) is False

    def test_empty_ua(self):
        assert is_webview('') is False

    def test_none_ua(self):
        assert is_webview(None) is False


class TestDetectPlatform:
    def test_iphone(self):
        assert detect_platform(SAFARI_IOS_UA) == 'ios'

    def test_ipad(self):
        assert detect_platform('Mozilla/5.0 (iPad; CPU OS 17_0) AppleWebKit') == 'ios'

    def test_ipod(self):
        assert detect_platform('Mozilla/5.0 (iPod touch; CPU iPhone OS) AppleWebKit') == 'ios'

    def test_android(self):
        assert detect_platform(CHROME_ANDROID_UA) == 'android'

    def test_desktop(self):
        assert detect_platform(CHROME_DESKTOP_UA) == 'other'

    def test_empty(self):
        assert detect_platform('') == 'other'

    def test_none(self):
        assert detect_platform(None) == 'other'


class TestWebviewRedirectIfNeeded:
    """Integration tests for the guard across real routes."""

    def test_line_redirected_from_auth_login(self, client):
        r = client.get('/auth/google/login', headers={'User-Agent': LINE_IOS_UA})
        assert r.status_code == 302
        assert '/auth/open-in-browser' in r.headers['Location']
        assert 'next=' in r.headers['Location']

    def test_safari_proceeds_to_google(self, client):
        r = client.get('/auth/google/login', headers={'User-Agent': SAFARI_IOS_UA})
        assert r.status_code == 302
        assert 'accounts.google.com' in r.headers['Location']

    def test_line_redirected_from_login_page(self, client):
        r = client.get('/login', headers={'User-Agent': LINE_IOS_UA})
        assert r.status_code == 302
        assert '/auth/open-in-browser' in r.headers['Location']

    def test_line_redirected_from_invite_page(self, client):
        r = client.get('/invite?code=ABC', headers={'User-Agent': LINE_IOS_UA})
        assert r.status_code == 302
        assert '/auth/open-in-browser' in r.headers['Location']
        # The original query string is preserved (url-encoded) in `next`.
        assert 'invite' in r.headers['Location']
        assert 'code' in r.headers['Location']

    def test_line_redirected_from_auth_invite_code(self, client):
        r = client.get('/auth/invite/code/XYZ', headers={'User-Agent': LINE_IOS_UA})
        assert r.status_code == 302
        assert '/auth/open-in-browser' in r.headers['Location']

    def test_lp_is_not_guarded(self, client):
        """Marketing page must stay accessible from in-app browsers."""
        r = client.get('/lp', headers={'User-Agent': LINE_IOS_UA})
        assert r.status_code == 200

    def test_open_in_browser_page_serves(self, client):
        r = client.get('/auth/open-in-browser?next=%2Flogin')
        assert r.status_code == 200
        assert b'open-btn' in r.data
        assert b'open-in-browser.js' in r.data
