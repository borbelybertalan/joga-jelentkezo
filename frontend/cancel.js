document.addEventListener('DOMContentLoaded', async () => {
    const details = document.getElementById('cancel-details');
    const confirmButton = document.getElementById('confirm-cancel');
    const token = new URLSearchParams(window.location.search).get('token');

    if (!token) {
        details.textContent = 'Hiányzik a lemondó link azonosítója.';
        confirmButton.disabled = true;
        return;
    }

    try {
        const response = await fetch(`/bookings/cancel/${encodeURIComponent(token)}`);
        const booking = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(booking.detail || 'A lemondó link érvénytelen.');

        const start = new Date(booking.start_time);
        const formattedStart = start.toLocaleString('hu-HU', { dateStyle: 'long', timeStyle: 'short' });
        details.textContent = `${booking.title} — ${formattedStart}`;
        if (booking.status === 'cancelled') {
            details.textContent += '. Ezt a foglalást már lemondták.';
            confirmButton.disabled = true;
        } else if (!booking.can_cancel) {
            details.textContent += '. Az órát 12 órán belül már nem lehet lemondani.';
            confirmButton.disabled = true;
        }
    } catch (error) {
        details.textContent = error.message;
        confirmButton.disabled = true;
    }

    confirmButton.addEventListener('click', async () => {
        if (!confirm('Biztosan lemondod ezt a foglalást?')) return;
        confirmButton.disabled = true;
        try {
            const response = await fetch(`/bookings/cancel/${encodeURIComponent(token)}`, { method: 'POST' });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(result.detail || 'A lemondás nem sikerült.');
            details.textContent = result.message;
        } catch (error) {
            details.textContent = error.message;
            confirmButton.disabled = false;
        }
    });
});
