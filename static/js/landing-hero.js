// Service Worker registration
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js');
}

// ============================================
// Hero: Flow Field (Perlin noise)
// ============================================
(() => {
    const canvas = document.getElementById('hero-canvas');
    const ctx = canvas.getContext('2d');
    const hero = document.getElementById('hero');
    let W, H, animId;

    function resize() {
        W = hero.offsetWidth;
        H = hero.offsetHeight;
        canvas.width = W;
        canvas.height = H;
        ctx.fillStyle = '#fff';
        ctx.fillRect(0, 0, W, H);
    }

    // --- Perlin noise ---
    const perm = new Uint8Array(512);
    {
        const p = new Uint8Array(256);
        for (let i = 0; i < 256; i++) p[i] = i;
        for (let i = 255; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [p[i], p[j]] = [p[j], p[i]];
        }
        for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
    }
    const grad2 = [[1,1],[-1,1],[1,-1],[-1,-1],[1,0],[-1,0],[0,1],[0,-1]];
    function noise(x, y) {
        const X = Math.floor(x) & 255, Y = Math.floor(y) & 255;
        const xf = x - Math.floor(x), yf = y - Math.floor(y);
        const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
        const aa = perm[perm[X] + Y] & 7, ab = perm[perm[X] + Y + 1] & 7;
        const ba = perm[perm[X + 1] + Y] & 7, bb = perm[perm[X + 1] + Y + 1] & 7;
        const dot = (g, dx, dy) => g[0] * dx + g[1] * dy;
        const x1 = dot(grad2[aa], xf, yf) * (1 - u) + dot(grad2[ba], xf - 1, yf) * u;
        const x2 = dot(grad2[ab], xf, yf - 1) * (1 - u) + dot(grad2[bb], xf - 1, yf - 1) * u;
        return x1 * (1 - v) + x2 * v;
    }

    // --- Particles ---
    const COUNT = 600;
    let particles = [];
    let t = 0;
    let vortices = [];

    function initParticles() {
        particles = [];
        for (let i = 0; i < COUNT; i++) {
            particles.push({
                x: Math.random() * W, y: Math.random() * H,
                px: 0, py: 0,
                age: Math.random() * 200,
                maxAge: 150 + Math.random() * 100,
            });
        }
    }

    resize();
    initParticles();
    window.addEventListener('resize', () => { resize(); initParticles(); });

    // --- Vortex on touch/click ---
    function addVortex(e) {
        const r = hero.getBoundingClientRect();
        if (e.touches) {
            for (const touch of e.touches)
                vortices.push({ x: touch.clientX - r.left, y: touch.clientY - r.top, t: 0 });
        } else {
            vortices.push({ x: e.clientX - r.left, y: e.clientY - r.top, t: 0 });
        }
    }
    hero.addEventListener('click', addVortex);
    hero.addEventListener('touchstart', addVortex, { passive: true });

    // --- Draw ---
    function draw() {
        ctx.fillStyle = 'rgba(255,255,255,0.06)';
        ctx.fillRect(0, 0, W, H);
        t += 0.003;

        vortices = vortices.filter(v => { v.t += 0.008; return v.t < 1; });

        for (const p of particles) {
            p.age++;
            if (p.age > p.maxAge) {
                p.x = Math.random() * W; p.y = Math.random() * H;
                p.px = p.x; p.py = p.y; p.age = 0;
                continue;
            }

            let angle = noise(p.x * 0.003, p.y * 0.003 + t) * Math.PI * 4;

            for (const v of vortices) {
                const dx = p.x - v.x, dy = p.y - v.y;
                const d = Math.sqrt(dx * dx + dy * dy);
                if (d < 180 && d > 0) {
                    const s = (1 - v.t) * (1 - d / 180) * 3;
                    angle += (Math.atan2(dy, dx) + Math.PI * 0.5) * s;
                }
            }

            p.px = p.x; p.py = p.y;
            p.x += Math.cos(angle) * 1.5;
            p.y += Math.sin(angle) * 1.5;

            if (p.x < 0 || p.x > W || p.y < 0 || p.y > H) {
                p.x = Math.random() * W; p.y = Math.random() * H;
                p.px = p.x; p.py = p.y; p.age = 0;
                continue;
            }

            const life = p.age / p.maxAge;
            const alpha = life < 0.1 ? life / 0.1 : life > 0.8 ? (1 - life) / 0.2 : 1;
            ctx.beginPath();
            ctx.moveTo(p.px, p.py);
            ctx.lineTo(p.x, p.y);
            ctx.strokeStyle = `rgba(59,130,246,${alpha * 0.35})`;
            ctx.lineWidth = 1;
            ctx.stroke();
        }

        animId = requestAnimationFrame(draw);
    }
    draw();
})();
