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
            showSetupTransition(data.name || name || '新しい組織');
        } else {
            errorEl.textContent = data.error || '組織の作成に失敗しました (' + res.status + ')';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.classList.remove('btn-loading');
        }
    } catch (e) {
        errorEl.textContent = '通信エラー: サーバーに接続できませんでした。';
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

function showSetupTransition(orgName) {
    const welcomeState = document.getElementById('welcome-state');
    const setupState = document.getElementById('setup-state');
    const orgNameEl = document.getElementById('setup-org-name');

    // Fade out welcome, show setup
    welcomeState.classList.add('fade-out');
    setTimeout(() => {
        welcomeState.style.display = 'none';
        orgNameEl.textContent = orgName;
        setupState.classList.add('active', 'fade-in');

        // Animate steps sequentially
        animateSteps();
    }, 300);
}

function animateSteps() {
    const steps = ['step-org', 'step-hours', 'step-ready'];
    let i = 0;

    function nextStep() {
        if (i >= steps.length) {
            // All done — redirect
            setTimeout(() => {
                window.location.href = '/';
            }, 600);
            return;
        }
        document.getElementById(steps[i]).classList.add('done');
        i++;
        setTimeout(nextStep, 500);
    }

    // Start first step after a brief pause
    setTimeout(nextStep, 400);
}
