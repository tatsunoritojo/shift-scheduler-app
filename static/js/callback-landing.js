(function() {
    var params = new URLSearchParams(window.location.search);
    var dest = params.get('dest') || '/';
    var joined = params.get('joined');

    if (joined === '1') {
        document.getElementById('callback-title').textContent = '組織に参加しました';
    }

    setTimeout(function() { window.location.href = dest; }, 1500);
})();
