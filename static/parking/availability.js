const panel = document.querySelector("#availability");
let refreshing = false;
async function refreshAvailability() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch(panel.dataset.url, {headers: {Accept: "application/json"}});
    if (!response.ok || response.redirected) throw new Error("No disponible");
    const data = await response.json();
    const container = panel.querySelector(".lots");
    const ids = new Set(data.lots.map(lot => String(lot.id)));
    container.querySelectorAll("[data-lot-id]").forEach(card => { if (!ids.has(card.dataset.lotId)) card.remove(); });
    for (const lot of data.lots) {
      let card = container.querySelector(`[data-lot-id="${lot.id}"]`);
      if (!card) {
        card = document.createElement("article");
        card.className = "card lot";
        card.dataset.lotId = lot.id;
        card.innerHTML = '<h3 data-name></h3><div class="number" data-free></div><p>espacios libres de <span data-capacity></span></p><div class="meter"><span data-meter></span></div><small data-occupied></small>';
      }
      card.querySelector("[data-name]").textContent = lot.name;
      card.querySelector("[data-free]").textContent = lot.free;
      card.querySelector("[data-capacity]").textContent = lot.capacity;
      card.querySelector("[data-occupied]").textContent = `${lot.occupied} vehículos en parqueo`;
      card.querySelector("[data-meter]").style.width = `${Math.min(100, 100 * lot.occupied / lot.capacity)}%`;
      container.append(card);
    }
    if (data.lots.length) container.querySelectorAll(":scope > p").forEach(item => item.remove());
    document.querySelector("#updated").textContent = `· ${data.updated_at}`;
  } catch {
    document.querySelector("#updated").textContent = "· Sin conexión; datos sin actualizar";
  } finally { refreshing = false; }
}
if (panel) { refreshAvailability(); setInterval(refreshAvailability, 5000); }

const countdown = document.querySelector("#arrival-countdown");
function remainingTime(milliseconds) {
  const total = Math.max(0, Math.ceil(milliseconds / 1000));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return `${days ? days + " d " : ""}${hours ? hours + " h " : ""}${minutes} min ${String(seconds).padStart(2, "0")} s`;
}
function updateCountdown() {
  const now = Date.now();
  const start = new Date(countdown.dataset.start).getTime();
  const deadline = new Date(countdown.dataset.deadline).getTime();
  countdown.textContent = now < start ? `Comienza en ${remainingTime(start - now)}` : now <= deadline ? `Ingreso disponible por ${remainingTime(deadline - now)}` : "Plazo de ingreso vencido";
}
if (countdown) { updateCountdown(); setInterval(updateCountdown, 1000); }
