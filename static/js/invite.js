(function () {
    'use strict';

    var ROLE_LABELS = {
        admin: '管理者',
        owner: '事業主',
        worker: 'アルバイト'
    };

    var ERROR_MESSAGES = {
        INVITE_CODE_NOT_FOUND: {
            title: '招待コードが見つかりません',
            message: 'この招待コードは存在しないか、無効になっています。管理者に新しい招待リンクを発行してもらってください。',
        },
        INVITE_CODE_DISABLED: {
            title: '招待コードが無効化されています',
            message: '管理者がこの招待コードを一時的に無効にしています。管理者にお問い合わせください。',
        },
        INVITATION_NOT_FOUND: {
            title: '招待が見つかりません',
            message: 'この招待リンクは存在しません。URLが正しいかご確認ください。',
        },
        INVITATION_USED: {
            title: 'この招待は使用済みです',
            message: 'この招待リンクは既に使用されています。複数回使用することはできません。',
        },
        INVITATION_EXPIRED: {
            title: '招待の有効期限が切れています',
            message: 'この招待リンクの有効期限が過ぎています。管理者に新しい招待を依頼してください。',
        },
        MISSING_PARAM: {
            title: '招待リンクが無効です',
            message: 'パラメータが不足しています。招待リンクが正しいかご確認ください。',
        },
    };

    var params = new URLSearchParams(window.location.search);
    var code = params.get('code');
    var token = params.get('token');

    if (!code && !token) {
        showError('MISSING_PARAM');
        return;
    }

    var query = code ? 'code=' + encodeURIComponent(code) : 'token=' + encodeURIComponent(token);

    fetch('/api/invite/info?' + query)
        .then(function (res) {
            if (!res.ok) {
                return res.json().then(function (data) {
                    var err = new Error(data.error || 'Unknown error');
                    err.code = data.code || 'UNKNOWN';
                    throw err;
                });
            }
            return res.json();
        })
        .then(function (data) {
            document.getElementById('org-name').textContent = data.organization_name;
            document.getElementById('role-label').textContent = ROLE_LABELS[data.role] || data.role;

            var loginBtn = document.getElementById('login-btn');
            loginBtn.href = data.login_url;
            loginBtn.addEventListener('click', function () {
                loginBtn.classList.add('btn-loading');
            });

            document.getElementById('invite-loading').style.display = 'none';
            var content = document.getElementById('invite-content');
            content.style.display = '';
            content.classList.add('fade-in');
        })
        .catch(function (err) {
            if (err.code && ERROR_MESSAGES[err.code]) {
                showError(err.code);
            } else if (err.message === 'Failed to fetch' || err.name === 'TypeError') {
                showNetworkError();
            } else {
                showError(null, err.message);
            }
        });

    function showError(errorCode, fallbackMessage) {
        document.getElementById('invite-loading').style.display = 'none';
        var container = document.getElementById('invite-error');

        var info = ERROR_MESSAGES[errorCode] || {
            title: 'エラーが発生しました',
            message: fallbackMessage || '招待情報の取得に失敗しました。',
        };

        container.innerHTML =
            '<div class="error-box">' +
            '<div class="error-box-title">' + info.title + '</div>' +
            '<div class="error-box-message">' + info.message + '</div>' +
            '<a href="/" class="btn btn-outline" style="text-decoration:none;">トップページへ</a>' +
            '</div>';
        container.style.display = '';
        container.classList.add('fade-in');
    }

    function showNetworkError() {
        document.getElementById('invite-loading').style.display = 'none';
        var container = document.getElementById('invite-error');

        container.innerHTML =
            '<div class="error-box">' +
            '<div class="error-box-title">通信エラー</div>' +
            '<div class="error-box-message">サーバーに接続できませんでした。インターネット接続を確認してください。</div>' +
            '<button class="btn btn-primary" onclick="location.reload()">再試行</button>' +
            '</div>';
        container.style.display = '';
        container.classList.add('fade-in');
    }
})();
