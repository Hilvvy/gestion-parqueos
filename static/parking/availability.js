const panel = document.querySelector("#availability");
let refreshing = false;
async function refreshAvailability() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch(panel.dataset.url, {headers: {Accept: "application/json"}});
    if (!response.ok || response.redirected) throw new Error("No disponible");
    const data = await response.json();
    data.lots.forEach((lot, index) => {
      const free = document.querySelector(`[data-free="${index}"]`);
      if (!free) return;
      free.textContent = lot.free;
      document.querySelector(`[data-occupied="${index}"]`).textContent = `${lot.occupied} vehículos en parqueo`;
      document.querySelector(`[data-meter="${index}"]`).style.width = `${100 * lot.occupied / lot.capacity}%`;
    });
    document.querySelector("#updated").textContent = `· ${data.updated_at}`;
  } catch {
    document.querySelector("#updated").textContent = "· Sin conexión; datos sin actualizar";
  } finally {
    refreshing = false;
  }
}
if (panel) { refreshAvailability(); setInterval(refreshAvailability, 5000); }
