fetch('/auth/me')
    .then(r => r.json())
    .then(data => {
        if (data.email) {
            document.getElementById('user-email').textContent =
                'ログイン中: ' + data.email;
        }
    })
    .catch(() => {});
