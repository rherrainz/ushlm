function updateTimers() {
  document.querySelectorAll('[data-expires]').forEach(el => {
    const remaining = new Date(el.dataset.expires).getTime() - Date.now();
    if (remaining <= 0) { el.textContent = 'Vencida · Actualizá para consultar disponibilidad'; return; }
    const minutes = Math.floor(remaining / 60000);
    el.textContent = `Vence en ${Math.floor(minutes / 60)} h ${minutes % 60} min · ${new Date(el.dataset.expires).toLocaleString('es-AR', {timeZone: 'America/Argentina/Ushuaia', hourCycle: 'h23'})} (Ushuaia)`;
  });
  document.querySelectorAll('[data-offer-expiry]').forEach(form => {
    if (new Date(form.dataset.offerExpiry).getTime() <= Date.now()) {
      const button = form.querySelector('button[value="request"]');
      if (button) { button.disabled = true; button.textContent = 'Oferta vencida'; }
    }
  });
}
updateTimers();
setInterval(updateTimers, 30000);
