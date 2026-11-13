(async () => {
    const state = document.getElementById('offline-state');
    const panel = document.getElementById('offline-console');
    const store = new ParkingStore();
    let context, csrf, syncing = false;
    const say = text => { if (state) state.textContent = text; };
    function textCell(row, value) { const cell = row.insertCell(); cell.textContent = value; return cell; }
    async function render() {
        if (!panel || !context) return;
        document.getElementById('offline-account').textContent = `${context.email} · Datos del ${new Date(context.updated_at).toLocaleString('es-CR')}`;
        const events = (await store.events()).filter(event => event.user === context.user);
        const pending = document.getElementById('offline-pending');
        pending.replaceChildren();
        for (const event of events) {
            const item = document.createElement('li');
            item.textContent = `${event.plate} · ${event.action === 'entry' ? 'Ingreso' : 'Salida'} · ${new Date(event.occurred_at).toLocaleString('es-CR')} · ${event.result || 'Pendiente'}`;
            pending.append(item);
        }
        const query = document.getElementById('offline-search').value.trim().toUpperCase();
        const body = document.getElementById('offline-rows'); body.replaceChildren();
        for (const original of context.rows.filter(row => !query || row.plate.includes(query) || row.code.toUpperCase() === query)) {
            const row = {...original};
            for (const event of events.filter(event => event.code === row.code && !event.result)) row.status = event.action === 'entry' ? 'inside' : 'completed';
            const tr = body.insertRow(); textCell(tr, row.plate);
            textCell(tr, `${row.lot} · ${new Date(row.start).toLocaleString('es-CR')} – ${new Date(row.end).toLocaleTimeString('es-CR')}`);
            const cell = textCell(tr, '');
            if (!['confirmed', 'inside'].includes(row.status)) { cell.textContent = 'Salida pendiente'; continue; }
            const button = document.createElement('button'); button.textContent = row.status === 'inside' ? 'Salida' : 'Ingreso';
            button.onclick = async () => {
                button.disabled = true;
                try {
                    const now = new Date();
                    if (row.status === 'confirmed' && (now < new Date(row.start) || now > new Date(row.deadline) || now >= new Date(row.end))) throw new Error('La cita está fuera de su horario o tolerancia.');
                    await store.put({id: crypto.randomUUID(), user: context.user, plate: row.plate, code: row.code, action: row.status === 'inside' ? 'exit' : 'entry', occurred_at: now.toISOString()});
                    say('Movimiento guardado en este dispositivo.'); await render(); await sync();
                } catch (error) { say(error.message); button.disabled = false; }
            };
            cell.append(button);
        }
    }
    async function refresh() {
        const response = await fetch('/acceso/contexto/', {cache: 'no-store'});
        if (!response.ok) { csrf = null; throw new Error('Inicia sesión como oficial para sincronizar.'); }
        const latest = await response.json(); csrf = latest.csrf;
        context = latest; await store.saveContext(latest);
    }
    async function sync() {
        if (syncing || !navigator.onLine) return;
        syncing = true;
        try {
            await refresh();
            await syncParkingEvents(await store.events(), context.user, event => fetch('/acceso/sincronizar/', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(event)
            }), event => store.put(event));
            await refresh(); say('Conectado. Movimientos sincronizados; revisa los conflictos.');
        } catch (error) { say(navigator.onLine ? error.message : 'Sin conexión. Los movimientos quedan guardados en este dispositivo.'); }
        finally { syncing = false; await render(); }
    }
    try {
        await store.open(); context = await store.context();
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
