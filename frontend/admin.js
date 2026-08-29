document.addEventListener('DOMContentLoaded', async function() {
    const calendarEl = document.getElementById('calendar');
    
    // Új óra ablak elemei
    const addModal = document.getElementById('add-class-modal');
    document.getElementById('open-add-modal-btn').addEventListener('click', () => addModal.classList.add('active'));
    document.getElementById('cancel-add-btn').addEventListener('click', () => addModal.classList.remove('active'));

    // Kezelő ablak elemei
    const manageModal = document.getElementById('manage-class-modal');
    const manageTitle = document.getElementById('manage-title');
    const manageTime = document.getElementById('manage-time');
    const studentsContainer = document.getElementById('manage-students-container');
    let currentManageClassId = null;

    document.getElementById('close-manage-btn').addEventListener('click', () => manageModal.classList.remove('active'));

    // 1. Új óra mentése
    document.getElementById('submit-add-btn').addEventListener('click', async () => {
        const title = document.getElementById('new-title').value.trim();
        const time = document.getElementById('new-time').value;
        const capacity = parseInt(document.getElementById('new-capacity').value);

        if (!title || !time || !capacity) return alert('Minden mezőt tölts ki!');

        const response = await fetch('http://127.0.0.1:8000/classes/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, start_time: new Date(time).toISOString(), max_capacity: capacity })
        });

        if (response.ok) {
            alert('Óra sikeresen meghirdetve!');
            location.reload();
        }
    });

    // 2. Óra törlése
    document.getElementById('delete-class-btn').addEventListener('click', async () => {
        if (!currentManageClassId) return;
        
        // Beépített böngészős megerősítés használata
        if (!confirm('Biztosan törölni szeretnéd a teljes órát és az összes jelentkezőt? Ez nem vonható vissza.')) return;

        const response = await fetch(`http://127.0.0.1:8000/admin/classes/${currentManageClassId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            alert('Óra törölve.');
            location.reload();
        }
    });

    // 3. Naptár betöltése
    const response = await fetch('http://127.0.0.1:8000/classes/');
    const classes = await response.json();

    const events = classes.map(yogaClass => ({
        id: yogaClass.id,
        title: `${yogaClass.title} (${yogaClass.free_spots} szabad)`,
        start: yogaClass.start_time,
        allDay: false
    }));

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
        locale: 'hu',
        slotMinTime: '06:00:00',
        slotMaxTime: '22:00:00',
        headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek' },
        events: events,
        eventClick: async function(info) {
            currentManageClassId = parseInt(info.event.id);
            manageTitle.textContent = info.event.title.split(' (')[0];
            manageTime.textContent = info.event.start.toLocaleString('hu-HU', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute:'2-digit' });
            
            studentsContainer.innerHTML = '<p>Betöltés...</p>';
            manageModal.classList.add('active'); // Ablak megnyitása

            // Tanulók lekérése
            const bookingsResponse = await fetch(`http://127.0.0.1:8000/classes/${currentManageClassId}/bookings/`);
            const bookings = await bookingsResponse.json();

            let activeHtml = '';
            let waitlistHtml = '';

            bookings.forEach(b => {
                const li = `<li><span>${b.name} (${b.email})</span> <button class="btn-delete-small" onclick="deleteStudent(${b.id})">Törlés</button></li>`;
                if (b.status === 'active') activeHtml += li;
                if (b.status === 'waitlisted') waitlistHtml += li;
            });

            studentsContainer.innerHTML = `
                <div style="margin-bottom: 15px;">
                    <strong>✅ Aktív résztvevők:</strong>
                    <ul class="admin-student-list" style="color: #2e7d32;">
                        ${activeHtml || '<li><i>Nincs aktív jelentkező.</i></li>'}
                    </ul>
                </div>
                <div>
                    <strong>⏳ Várólista:</strong>
                    <ul class="admin-student-list" style="color: #ef6c00;">
                        ${waitlistHtml || '<li><i>Üres a várólista.</i></li>'}
                    </ul>
                </div>
            `;
        }
    });

    calendar.render();
});

// Tanuló törlése funkció (globálisan elérhetővé téve az inline onclick miatt)
window.deleteStudent = async function(bookingId) {
    if (!confirm('Biztosan eltávolítod a tanítványt?')) return;

    const response = await fetch(`http://127.0.0.1:8000/admin/bookings/${bookingId}`, { method: 'DELETE' });
    if (response.ok) {
        alert('Tanítvány eltávolítva.');
        location.reload(); 
    }
};