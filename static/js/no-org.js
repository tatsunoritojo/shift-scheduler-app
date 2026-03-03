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
    errorEl.style.display = 'none';

    try {
        const res = await fetch('/api/organizations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name || undefined }),
        });
        const data = await res.json();

        if (res.ok) {
            window.location.href = '/';
        } else {
            errorEl.textContent = data.error || `組織の作成に失敗しました (${res.status})`;
            errorEl.style.display = 'block';
            btn.disabled = false;
        }
    } catch (e) {
        errorEl.textContent = '通信エラーが発生しました: ' + e.message;
        errorEl.style.display = 'block';
        btn.disabled = false;
    }
});

// Allow Enter key to submit
document.getElementById('org-name')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('create-org-btn')?.click();
    }
});
