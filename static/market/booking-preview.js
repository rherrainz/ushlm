// Integer cents avoid floating-point rounding (e.g. 19.99 × 3).
// Informational only: the server validates the signed offer and recalculates.
document.querySelectorAll('[data-booking-preview]').forEach(form => {
  const input = form.querySelector('[name="quantity"]');
  const output = form.querySelector('[data-booking-total]');
  const update = () => {
    if (!/^[1-9]\d*$/.test(input.value) || BigInt(input.value) > 2147483647n) {
      output.textContent = 'Ingresá una cantidad entera positiva';
      return;
    }
    const cents = BigInt(form.dataset.unitCents) * BigInt(input.value);
    output.textContent = `${form.dataset.currency} ${cents / 100n},${String(cents % 100n).padStart(2, '0')}`;
  };
  input.addEventListener('input', update);
  update();
});
