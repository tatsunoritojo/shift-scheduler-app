(function () {
    'use strict';

    var ROLE_LABELS = {
        admin: '管理者',
        owner: '事業主',
        worker: 'アルバイト'
    };

    var params = new URLSearchParams(window.location.search);
    var code = params.get('code');
    var token = params.get('token');

    if (!code && !token) {
        showError('招待リンクが無効です。パラメータが不足しています。');
        return;
    }

    var query = code ? 'code=' + encodeURIComponent(code) : 'token=' + encodeURIComponent(token);

    fetch('/api/invite/info?' + query)
        .then(function (res) {
            if (!res.ok) {
                return res.json().then(function (data) {
                    throw new Error(data.error || '招待が無効または期限切れです');
                });
            }
            return res.json();
        })
        .then(function (data) {
            document.getElementById('org-name').textContent = data.organization_name;
            document.getElementById('role-label').textContent = ROLE_LABELS[data.role] || data.role;
            document.getElementById('login-btn').href = data.login_url;
            document.getElementById('invite-loading').style.display = 'none';
            document.getElementById('invite-content').style.display = '';
        })
        .catch(function (err) {
            showError(err.message || '招待情報の取得に失敗しました');
        });

    function showError(msg) {
        document.getElementById('invite-loading').style.display = 'none';
        document.getElementById('error-message').textContent = msg;
        document.getElementById('invite-error').style.display = '';
    }
})();
