fetch('/auth/me')
    .then(r => r.json())
    .then(data => {
        if (data.email) {
            document.getElementById('user-email').textContent =
                'ログイン中: ' + data.email;
        }
        // Pre-fill org name suggestion
        const nameInput = document.getElementById('org-name');
        if (nameInput && data.display_name) {
            nameInput.placeholder = data.display_name + ' の組織';
        }
    })
    .catch(() => {});

document.getElementById('create-org-btn')?.addEventListener('click', async () => {
    const btn = document.getElementById('create-org-btn');
    const nameInput = document.getElementById('org-name');
    const errorEl = document.getElementById('create-error');
    const name = nameInput.value.trim();

    btn.disabled = true;
    btn.classList.add('btn-loading');
    errorEl.style.display = 'none';

    try {
        const res = await fetch('/api/organizations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name || undefined }),
        });
        const data = await res.json();

        if (res.ok) {
            // Show success state
            const formSection = document.getElementById('create-form-section');
            const successSection = document.getElementById('create-success');
            const divider = document.querySelector('.divider');
            const steps = document.querySelector('.steps');

            if (formSection) formSection.style.display = 'none';
            if (divider) divider.style.display = 'none';
            if (steps) steps.style.display = 'none';

            document.getElementById('success-org-name').textContent = data.name || name || '新しい組織';
            if (successSection) {
                successSection.style.display = '';
                successSection.classList.add('fade-in');
            }

            setTimeout(() => { window.location.href = '/'; }, 1500);
        } else {
            errorEl.textContent = data.error || '組織の作成に失敗しました (' + res.status + ')';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.classList.remove('btn-loading');
        }
    } catch (e) {
        errorEl.textContent = '通信エラー: サーバーに接続できませんでした。インターネット接続を確認してください。';
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.classList.remove('btn-loading');
    }
});

// Allow Enter key to submit
document.getElementById('org-name')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('create-org-btn')?.click();
    }
});
