(async () => {
    const state = document.getElementById('offline-state');
    const panel = document.getElementById('offline-console');
    const store = new ParkingStore();
    let context, csrf, syncing = false, sessionEpoch = 0;
    const say = text => { if (state) state.textContent = text; };
    function textCell(row, value) { const cell = row.insertCell(); cell.textContent = value; return cell; }
    async function render() {
        if (!panel) return;
        if (!context) {
            document.getElementById('offline-account').textContent = '';
            document.getElementById('offline-pending').replaceChildren();
            document.getElementById('offline-rows').replaceChildren();
            return;
        }
        const snapshot = context;
        const events = (await store.events()).filter(event => event.user === snapshot.user);
        if (context !== snapshot) return;
        document.getElementById('offline-account').textContent = `${snapshot.email} · Datos del ${new Date(snapshot.updated_at).toLocaleString('es-CR', {timeZone: 'America/Costa_Rica'})}`;
        const pending = document.getElementById('offline-pending');
        pending.replaceChildren();
        for (const event of events) {
            const item = document.createElement('li');
            item.textContent = `${event.plate} · ${event.action === 'entry' ? 'Ingreso' : 'Salida'} · ${new Date(event.occurred_at).toLocaleString('es-CR', {timeZone: 'America/Costa_Rica'})} · ${event.result || 'Pendiente'}`;
            pending.append(item);
        }
        let query = document.getElementById('offline-search').value.trim().toUpperCase();
        const confirmationCode = query.match(/\/CONFIRMACION\/([0-9A-F-]{36})\/?(?:[?#].*)?$/);
        if (confirmationCode) query = confirmationCode[1];
        const body = document.getElementById('offline-rows'); body.replaceChildren();
        for (const original of snapshot.rows.filter(row => !query || row.plate.includes(query) || row.code.toUpperCase() === query)) {
            const row = {...original, status: parkingPendingStatus(original, events)};
            const tr = body.insertRow(); textCell(tr, row.plate);
            textCell(tr, `${row.lot} · ${new Date(row.start).toLocaleString('es-CR', {timeZone: 'America/Costa_Rica'})} – ${new Date(row.end).toLocaleTimeString('es-CR', {timeZone: 'America/Costa_Rica'})}`);
            const cell = textCell(tr, '');
            if (!['confirmed', 'inside'].includes(row.status)) { cell.textContent = 'Salida pendiente'; continue; }
            const button = document.createElement('button'); button.textContent = row.status === 'inside' ? 'Salida' : 'Ingreso';
            button.onclick = async () => {
                button.disabled = true;
                try {
                    if (!context || context.user !== snapshot.user) throw new Error('La sesión cambió. Vuelve a iniciar sesión.');
                    const now = new Date();
                    if (row.status === 'confirmed' && (now < new Date(row.start) || now > new Date(row.deadline) || now >= new Date(row.end))) throw new Error('La cita está fuera de su horario o tolerancia.');
                    await store.put({id: crypto.randomUUID(), user: snapshot.user, plate: row.plate, code: row.code, action: row.status === 'inside' ? 'exit' : 'entry', occurred_at: now.toISOString()});
                    say('Movimiento guardado en este dispositivo.'); await render(); await sync();
                } catch (error) { say(error.message); button.disabled = false; }
            };
            cell.append(button);
        }
    }
    async function lockDevice(message) {
        sessionEpoch++; context = null; csrf = null;
        await render(); say(message);
        await store.clearContext();
    }
    async function refresh() {
        const epoch = sessionEpoch;
        const response = await fetch('/acceso/contexto/', {cache: 'no-store'});
        if (!response.ok) {
            if (response.status === 403) await lockDevice('Sesión no disponible. Inicia sesión de nuevo; los movimientos pendientes se conservan.');
            throw new Error('Inicia sesión como oficial para sincronizar.');
        }
        const latest = await response.json();
        if (epoch !== sessionEpoch) throw new Error('La sesión cambió. Vuelve a iniciar sesión.');
        csrf = latest.csrf;
        context = latest; await store.saveContext(latest);
    }
    async function sync() {
        if (syncing || !navigator.onLine) return;
        syncing = true;
        try {
            await refresh();
            const user = context.user, epoch = sessionEpoch;
            await syncParkingEvents(await store.events(), user, event => {
                if (epoch !== sessionEpoch || !context || context.user !== user) throw new Error('La sesión cambió. Los movimientos pendientes se conservan.');
                return fetch('/acceso/sincronizar/', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(event)
                });
            }, event => store.put(event));
            await refresh(); say('Conectado. Movimientos sincronizados; revisa los conflictos.');
        } catch (error) { say(navigator.onLine ? error.message : 'Sin conexión. Los movimientos quedan guardados en este dispositivo.'); }
        finally { syncing = false; await render(); }
    }
    try {
        await store.open(); context = await store.context();
        if ('BroadcastChannel' in window) {
            const channel = new BroadcastChannel('parking-device-session');
            channel.onmessage = event => { if (event.data === 'logout') lockDevice('Sesión cerrada. Los movimientos pendientes se conservan.').catch(error => say(error.message)); };
        }
        if ('serviceWorker' in navigator) navigator.serviceWorker.register('/service-worker.js').catch(() => say('No se pudo preparar la página sin conexión. Abre la aplicación desde localhost o HTTPS.'));
        if (panel) {
            document.getElementById('offline-search').oninput = render;
            document.getElementById('offline-sync').onclick = sync;
            document.getElementById('offline-clear').onclick = async () => {
                if (!context) return;
                for (const event of await store.events()) if (event.user === context.user && event.result === 'Sincronizado') await store.remove(event.id);
                await render();
            };
        }
        await render(); await sync();
        if (!context) say('Conéctate e inicia sesión como oficial para preparar este dispositivo.');
        else if (!navigator.onLine) say('Sin conexión. Registros pendientes de validación.');
        window.addEventListener('online', sync);
        window.addEventListener('offline', () => say('Sin conexión. Usa Movimientos del dispositivo.'));
        setInterval(sync, 15000);
    } catch (error) { say(`No se pudo preparar el almacenamiento: ${error.message}`); }
})();
