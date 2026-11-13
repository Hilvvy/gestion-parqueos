/* Cada escritura termina antes de mostrar que el movimiento quedó guardado. */
globalThis.ParkingStore = class ParkingStore {
    async open() {
        this.db = await new Promise((resolve, reject) => {
            const request = indexedDB.open('parking-device', 1);
            request.onupgradeneeded = () => {
                request.result.createObjectStore('events', {keyPath: 'id'});
                request.result.createObjectStore('context');
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    async transaction(store, operation, write = false) {
        return new Promise((resolve, reject) => {
            const tx = this.db.transaction(store, write ? 'readwrite' : 'readonly');
            let result;
            const request = operation(tx.objectStore(store));
            request.onsuccess = () => { result = request.result; };
            tx.oncomplete = () => resolve(result);
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error('No se pudo guardar el movimiento.'));
        });
    }
    context() { return this.transaction('context', store => store.get('current')); }
    saveContext(value) {
        const {csrf, ...safe} = value;
        return this.transaction('context', store => store.put(safe, 'current'), true);
    }
    events() { return this.transaction('events', store => store.getAll()); }
    put(event) { return this.transaction('events', store => store.put(event), true); }
    remove(id) { return this.transaction('events', store => store.delete(id), true); }
};

globalThis.syncParkingEvents = async function(events, user, send, save) {
    for (const event of events.filter(row => row.user === user && !row.result).sort((a, b) => a.occurred_at.localeCompare(b.occurred_at))) {
        const response = await send(event);
        if (response.status === 404 || response.status === 409) {
            const result = await response.json();
            await save({...event, result: `Conflicto: ${result.error}`});
            continue;
        }
        if (!response.ok) throw new Error(response.status === 403 ? 'Inicia sesión de nuevo para sincronizar.' : 'No se pudo sincronizar; los registros siguen guardados.');
        const result = await response.json();
        await save({...event, result: result.accepted ? 'Sincronizado' : `Conflicto: ${result.error}`});
    }
};
