const reservationForm = document.querySelector("#reservation-form");
let recommendationRequest;
async function showRecommendation() {
  const start = reservationForm.elements.starts_at.value;
  const end = reservationForm.elements.ends_at.value;
  const output = document.querySelector("#recommendation");
  if (recommendationRequest) recommendationRequest.abort();
  if (!start || !end) { output.textContent = ""; return; }
  recommendationRequest = new AbortController();
  const url = new URL(reservationForm.dataset.recommendationUrl, location.origin);
  url.search = new URLSearchParams({starts_at: start, ends_at: end});
  try {
    const response = await fetch(url, {signal: recommendationRequest.signal});
    if (response.redirected) throw new Error("Sesión terminada");
    const data = await response.json();
    output.textContent = data.error || (data.recommended ? `Recomendado: ${data.recommended.name} · ${data.recommended.free} espacios disponibles` : "Sin espacios para ese horario.");
  } catch (error) {
    if (error.name !== "AbortError") output.textContent = "No se pudo consultar la recomendación.";
  }
}
if (reservationForm) {
  reservationForm.elements.starts_at.addEventListener("change", showRecommendation);
  reservationForm.elements.ends_at.addEventListener("change", showRecommendation);
  showRecommendation();
}
