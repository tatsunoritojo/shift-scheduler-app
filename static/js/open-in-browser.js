(function () {
    'use strict';

    function getNextPath() {
        var params = new URLSearchParams(window.location.search);
        var next = params.get('next') || '/';
        // Security: only accept same-origin relative paths.
        if (next.indexOf('//') === 0 || next.indexOf('://') !== -1) {
            next = '/';
        }
        if (next.charAt(0) !== '/') {
            next = '/' + next;
        }
        return next;
    }

    function detectPlatform() {
        var ua = navigator.userAgent || '';
        if (/iPhone|iPad|iPod/i.test(ua)) return 'ios';
        if (/Android/i.test(ua)) return 'android';
        return 'other';
    }

    var nextPath = getNextPath();
    var platform = detectPlatform();
    var host = window.location.host;
    var fullUrl = window.location.origin + nextPath;

    var openBtn = document.getElementById('open-btn');
    var openLabel = document.getElementById('open-label');
    var copyBtn = document.getElementById('copy-btn');
    var toast = document.getElementById('toast');
    var urlBox = document.getElementById('url-box');
    var fallbackBanner = document.getElementById('fallback-banner');

    if (platform === 'ios') {
        openBtn.href = 'x-safari-https://' + host + nextPath;
        openLabel.textContent = 'Safariで開く';
    } else if (platform === 'android') {
        // S.browser_fallback_url lets Android open the URL in the default
        // browser if Chrome isn't installed, instead of silently doing nothing.
        var fallbackParam = 'S.browser_fallback_url=' + encodeURIComponent(fullUrl);
        openBtn.href =
            'intent://' + host + nextPath +
            '#Intent;scheme=https;package=com.android.chrome;' +
            fallbackParam + ';end';
        openLabel.textContent = 'Chromeで開く';
    } else {
        openBtn.href = fullUrl;
        openBtn.target = '_blank';
        openLabel.textContent = 'ブラウザで開く';
    }

    function showToast() {
        toast.classList.add('show');
        setTimeout(function () {
            toast.classList.remove('show');
        }, 2000);
    }

    function showUrlFallback() {
        urlBox.textContent = fullUrl;
        urlBox.classList.add('show');
    }

    copyBtn.addEventListener('click', function () {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(fullUrl).then(
                function () {
                    showToast();
                    showUrlFallback();
                },
                function () {
                    showUrlFallback();
                }
            );
        } else {
            showUrlFallback();
        }
    });

    // Scheme-failure detection: if the page remains visible 2s after the user
    // taps the open button, the scheme (x-safari-https:// / intent://) was
    // silently blocked (typical on Instagram / Facebook iOS). Auto-reveal the
    // copy-URL fallback so the user isn't left staring at a dead button.
    openBtn.addEventListener('click', function () {
        var tapTime = Date.now();
        var wentHidden = false;

        function onVisibilityChange() {
            if (document.hidden) {
                wentHidden = true;
            }
        }
        document.addEventListener('visibilitychange', onVisibilityChange);

        setTimeout(function () {
            document.removeEventListener('visibilitychange', onVisibilityChange);
            if (!wentHidden && Date.now() - tapTime >= 1900) {
                if (fallbackBanner) fallbackBanner.classList.add('show');
                showUrlFallback();
            }
        }, 2000);
    });
})();
