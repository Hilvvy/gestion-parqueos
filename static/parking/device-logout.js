document.querySelectorAll('form[action="/logout/"]').forEach(form => {
    form.addEventListener('submit', event => {
        if (!('indexedDB' in window)) return;
        event.preventDefault();
        if ('BroadcastChannel' in window) {
            const channel = new BroadcastChannel('parking-device-session');
            channel.postMessage('logout'); channel.close();
        }
        const request = indexedDB.open('parking-device', 1);
        const finish = () => HTMLFormElement.prototype.submit.call(form);
        request.onerror = finish;
        request.onupgradeneeded = () => request.transaction.abort();
        request.onsuccess = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains('context')) { db.close(); finish(); return; }
            const tx = db.transaction('context', 'readwrite');
            tx.objectStore('context').clear();
            tx.oncomplete = tx.onerror = () => { db.close(); finish(); };
        };
    });
});
