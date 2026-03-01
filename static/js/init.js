// Common initialization: Service Worker registration + Lucide icons
if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js');
}
document.addEventListener('DOMContentLoaded', function() {
    if (window.lucide) {
        lucide.createIcons();
    }
});
