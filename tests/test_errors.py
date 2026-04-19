"""Tests for error helpers: wants_json() and render_error_page()."""

from app.utils.errors import render_error_page, wants_json


class TestWantsJson:
    """/api/* is always JSON; other paths default to HTML unless JSON is preferred."""

    def test_api_path_always_json(self, app):
        with app.test_request_context('/api/anything', headers={'Accept': 'text/html'}):
            assert wants_json() is True

    def test_page_path_wildcard_accept_is_html(self, app):
        """Bare Accept: */* on a page route should default to HTML (not JSON)."""
        with app.test_request_context('/some-page', headers={'Accept': '*/*'}):
            assert wants_json() is False

    def test_page_path_no_accept_is_html(self, app):
        with app.test_request_context('/some-page'):
            assert wants_json() is False

    def test_page_path_browser_accept_is_html(self, app):
        with app.test_request_context('/some-page', headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }):
            assert wants_json() is False

    def test_page_path_explicit_json_wins(self, app):
        with app.test_request_context('/some-page', headers={'Accept': 'application/json'}):
            assert wants_json() is True

    def test_page_path_json_higher_quality_than_html(self, app):
        with app.test_request_context('/some-page', headers={
            'Accept': 'application/json, text/html;q=0.5',
        }):
            assert wants_json() is True


class TestRenderErrorPage:
    """User-facing HTML error responses. Must be safe (XSS) and recoverable."""

    def test_content_type_is_html(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(title='t', message='m')
            assert 'text/html' in resp.content_type

    def test_default_status_is_400(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(title='t', message='m')
            assert resp.status_code == 400

    def test_custom_status(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(title='t', message='m', status=404)
            assert resp.status_code == 404

    def test_title_escaped(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(
                title='<script>alert(1)</script>',
                message='safe',
            )
            body = resp.data.decode('utf-8')
            assert '<script>alert(1)</script>' not in body
            assert '&lt;script&gt;alert(1)&lt;/script&gt;' in body

    def test_message_escaped(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(
                title='safe',
                message='<img src=x onerror=alert(2)>',
            )
            body = resp.data.decode('utf-8')
            assert '<img src=x onerror=alert(2)>' not in body
            assert '&lt;img src=x' in body

    def test_back_url_escaped(self, app):
        """Defense-in-depth: back_url must be escaped even though callers set it."""
        with app.test_request_context('/'):
            resp = render_error_page(
                title='t', message='m',
                back_url='/foo"><script>alert(1)</script>',
            )
            body = resp.data.decode('utf-8')
            assert '<script>alert(1)</script>' not in body

    def test_back_url_and_label_rendered(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(
                title='t', message='m',
                back_url='/custom', back_label='戻る',
            )
            body = resp.data.decode('utf-8')
            assert 'href="/custom"' in body
            assert '戻る' in body

    def test_detail_optional(self, app):
        with app.test_request_context('/'):
            with_detail = render_error_page(title='t', message='m', detail='extra info')
            without = render_error_page(title='t', message='m')
            assert b'extra info' in with_detail.data
            assert b'extra info' not in without.data

    def test_detail_escaped(self, app):
        with app.test_request_context('/'):
            resp = render_error_page(
                title='t', message='m',
                detail='<script>bad()</script>',
            )
            body = resp.data.decode('utf-8')
            assert '<script>bad()</script>' not in body
