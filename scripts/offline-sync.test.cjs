const {test} = require('node:test');
const assert = require('node:assert/strict');
require('../static/parking/offline-store.js');
const event = (id, user = 1, time = '2026-11-12T20:00:00Z') => ({id, user, occurred_at: time});
const response = (accepted, error = '') => ({ok: true, json: async () => ({accepted, error})});

test('envía solo la cuenta actual, pendientes y en orden temporal', async () => {
    const sent = [], saved = [];
    await syncParkingEvents([event('exit', 1, '2026-11-12T20:01:00Z'), event('other', 2), {...event('done'), result: 'Sincronizado'}, event('entry')], 1,
        async row => { sent.push(row.id); return response(true); }, async row => saved.push(row));
    assert.deepEqual(sent, ['entry', 'exit']);
    assert.ok(saved.every(row => row.result === 'Sincronizado'));
});
test('si se pierde la respuesta, conserva el UUID para el reintento', async () => {
    const queue = [event('same-uuid')], sent = [];
    await assert.rejects(syncParkingEvents(queue, 1, async row => { sent.push(row.id); throw Error('sin red'); }, async () => assert.fail('no debe confirmar')));
    await syncParkingEvents(queue, 1, async row => { sent.push(row.id); return response(true); }, async row => { queue[0] = row; });
    await syncParkingEvents(queue, 1, async () => assert.fail('no debe reenviar'), async () => {});
    assert.deepEqual(sent, ['same-uuid', 'same-uuid']);
});
test('los conflictos visibles no bloquean el siguiente movimiento', async () => {
    const saved = [];
    await syncParkingEvents([event('bad'), event('good')], 1, async row => row.id === 'bad' ? response(false, 'Sin cupo') : response(true), async row => saved.push(row));
    assert.equal(saved[0].result, 'Conflicto: Sin cupo');
    assert.equal(saved[1].result, 'Sincronizado');
});
test('sesión vencida mantiene la cola y detiene la sincronización', async () => {
    await assert.rejects(syncParkingEvents([event('a'), event('b')], 1, async () => ({ok: false, status: 403}), async () => assert.fail()), /Inicia sesión/);
});
test('revocación de permiso queda visible y no bloquea la cola', async () => {
    const saved = [];
    await syncParkingEvents([event('revoked')], 1, async () => ({ok: false, status: 404, json: async () => ({error: 'Parqueo no asignado'})}), async row => saved.push(row));
    assert.equal(saved[0].result, 'Conflicto: Parqueo no asignado');
});
