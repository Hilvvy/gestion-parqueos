const alertsPanel = document.querySelector("#security-alerts");
let updatingAlerts = false;
const alertTime = value => new Intl.DateTimeFormat("es-CR", {hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/Costa_Rica"}).format(new Date(value));
async function refreshAlerts() {
  if (updatingAlerts) return;
  updatingAlerts = true;
  try {
    const response = await fetch(alertsPanel.dataset.url);
    if (!response.ok || response.redirected) throw new Error("Sin sesión");
    const data = await response.json();
    document.querySelector("#upcoming-count").textContent = data.upcoming_count;
    document.querySelector("#pending-count").textContent = data.pending_count;
    const list = document.querySelector("#arrival-list");
    list.replaceChildren();
    for (const [rows, pending] of [[data.pending, true], [data.upcoming, false]]) {
      for (const row of rows) {
        const item = document.createElement("li");
        const time = pending ? row.entry_deadline : row.starts_at;
        item.textContent = `${row.plate} · ${row.parking_lot} · ${pending ? "ingreso hasta" : "llega"} ${time ? alertTime(time) : "—"}`;
        list.append(item);
      }
    }
    document.querySelector("#alerts-updated").textContent = data.updated_at;
  } catch {
    document.querySelector("#alerts-updated").textContent = "Sin conexión; datos anteriores";
  } finally { updatingAlerts = false; }
}
if (alertsPanel) { refreshAlerts(); setInterval(refreshAlerts, 5000); }
