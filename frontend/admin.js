document.addEventListener('DOMContentLoaded', async function() {
    const loginScreen = document.getElementById('login-screen');
    const appContent = document.getElementById('app-content');
    const loginError = document.getElementById('login-error');
    let authHeader = '';

    async function fetchAdmin(url, options = {}) {
        options.headers = { ...options.headers, 'Authorization': authHeader };
        const response = await fetch(url, options);
        if (response.status === 401) {
            sessionStorage.removeItem('jogaAuth');
            location.reload();
        }
        return response;
    }

    async function initializeApp(savedAuth) {
        authHeader = savedAuth;
        const response = await fetch('http://127.0.0.1:8000/admin/verify', { headers: { 'Authorization': authHeader } });
        if (response.ok) {
            loginScreen.style.display = 'none';
            appContent.style.display = 'block';
            loadCalendar();
        } else {
            sessionStorage.removeItem('jogaAuth');
            loginScreen.style.display = 'flex';
        }
    }

    const storedAuth = sessionStorage.getItem('jogaAuth');
    if (storedAuth) initializeApp(storedAuth);

    document.getElementById('login-btn').addEventListener('click', async () => {
        const user = document.getElementById('login-user').value.trim();
        const pass = document.getElementById('login-pass').value.trim();
        if (!user || !pass) return;

        const attemptAuth = 'Basic ' + btoa(user + ':' + pass);
        const response = await fetch('http://127.0.0.1:8000/admin/verify', { headers: { 'Authorization': attemptAuth } });
        if (response.ok) {
            sessionStorage.setItem('jogaAuth', attemptAuth);
            loginError.style.display = 'none';
            initializeApp(attemptAuth);
        } else {
            loginError.style.display = 'block';
        }
    });

    document.getElementById('logout-btn').addEventListener('click', () => {
        sessionStorage.removeItem('jogaAuth');
        location.reload();
    });

    async function loadCalendar() {
        const calendarEl = document.getElementById('calendar');

        const addModal = document.getElementById('add-class-modal');
        document.getElementById('open-add-modal-btn').addEventListener('click', () => addModal.classList.add('active'));
        document.getElementById('cancel-add-btn').addEventListener('click', () => addModal.classList.remove('active'));

        const manageModal = document.getElementById('manage-class-modal');
        const manageTitle = document.getElementById('manage-title');
        const manageTime = document.getElementById('manage-time');
        const manageInfo = document.getElementById('manage-info');
        const studentsContainer = document.getElementById('manage-students-container');
        let currentManageClassId = null;

        document.getElementById('close-manage-btn').addEventListener('click', () => manageModal.classList.remove('active'));

        document.getElementById('submit-add-btn').addEventListener('click', async () => {
            const title = document.getElementById('new-title').value.trim();
            const time = document.getElementById('new-time').value;
            const capacity = parseInt(document.getElementById('new-capacity').value);
            const instructor = document.getElementById('new-instructor').value.trim() || null;
            const note = document.getElementById('new-note').value.trim() || null;
            const zoomAvailable = document.getElementById('new-zoom').checked;

            if (!title || !time || !capacity) return alert('Minden mezőt tölts ki!');

            // A datetime-local értéket szándékosan változtatás nélkül küldjük el.
            // Így a backend helyi magyar időként tudja tárolni, és nem történik
            // UTC-konverzió. Ez az óraátállítás után is helyesen működik.
            const response = await fetchAdmin('http://127.0.0.1:8000/classes/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title,
                    start_time: time,
                    max_capacity: capacity,
                    instructor,
                    note,
                    zoom_available: zoomAvailable
                })
            });

            if (response.ok) {
                alert('Óra sikeresen meghirdetve!');
                location.reload();
            } else {
                const data = await response.json();
                alert('Hiba történt: ' + (data.detail || 'Ismeretlen hiba'));
            }
        });

        document.getElementById('delete-class-btn').addEventListener('click', async () => {
            if (!currentManageClassId) return;
            if (!confirm('Biztosan törölni szeretnéd a teljes órát és az összes jelentkezőt? Ez nem vonható vissza.')) return;

            const response = await fetchAdmin(`http://127.0.0.1:8000/admin/classes/${currentManageClassId}`, { method: 'DELETE' });
            if (response.ok) {
                alert('Óra törölve.');
                location.reload();
            }
        });

        window.deleteStudent = async function(bookingId) {
            if (!confirm('Biztosan eltávolítod a tanítványt?')) return;
            const response = await fetchAdmin(`http://127.0.0.1:8000/admin/bookings/${bookingId}`, { method: 'DELETE' });
            if (response.ok) {
                alert('Tanítvány eltávolítva.');
                location.reload();
            }
        };

        const response = await fetchAdmin('http://127.0.0.1:8000/classes/');
        const classes = await response.json();

        const events = classes.map(yogaClass => {
            const event = {
                id: yogaClass.id,
                title: yogaClass.title,
                start: yogaClass.start_time,
                allDay: false,
                extendedProps: {
                    freeSpots: yogaClass.free_spots,
                    instructor: yogaClass.instructor,
                    note: yogaClass.note,
                    zoomAvailable: yogaClass.zoom_available
                }
            };

            const startDate = new Date(yogaClass.start_time);
            if (startDate.getHours() === 6 && startDate.getMinutes() === 20) {
                event.end = yogaClass.end_time || new Date(startDate.getTime() + 30 * 60 * 1000).toISOString();
            }

            if (yogaClass.title.toLowerCase().includes('légzés')) {
                event.classNames = ['breathing-event'];
            }

            return event;
        });

        const calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'timeGridWeek',
            locale: 'hu',
            slotMinTime: '06:00:00',
            slotMaxTime: '22:00:00',
            headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek' },
            events: events,
            eventClick: async function(info) {
                currentManageClassId = parseInt(info.event.id);
                const props = info.event.extendedProps;
                manageTitle.textContent = info.event.title;

                const start = info.event.start;
                const end = info.event.end;
                const dateText = start.toLocaleDateString('hu-HU', { year: 'numeric', month: 'long', day: 'numeric' });
                const startText = start.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' });
                const endText = end ? end.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' }) : '';
                manageTime.textContent = `${dateText} • ${startText}${endText ? ` - ${endText}` : ''}`;

                let infoHtml = `<div class="admin-class-info">
                    <div><strong>${props.freeSpots} szabad hely</strong></div>
                    ${props.instructor ? `<div class="class-instructor"><em>${props.instructor}</em></div>` : ''}
                    ${props.note ? `<div class="class-note">${props.note}</div>` : ''}
                    ${props.zoomAvailable ? `<div class="class-zoom">Zoom-on is</div>` : ''}
                </div>`;
                manageInfo.innerHTML = infoHtml;

                studentsContainer.innerHTML = '<p>Betöltés...</p>';
                manageModal.classList.add('active');

                const bookingsResponse = await fetchAdmin(`http://127.0.0.1:8000/classes/${currentManageClassId}/bookings/`);
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
                        <strong>Aktív résztvevők:</strong>
                        <ul class="admin-student-list" style="color: #2e7d32;">
                            ${activeHtml || '<li><i>Nincs aktív jelentkező.</i></li>'}
                        </ul>
                    </div>
                    <div>
                        <strong>Várólista:</strong>
                        <ul class="admin-student-list" style="color: #ef6c00;">
                            ${waitlistHtml || '<li><i>Üres a várólista.</i></li>'}
                        </ul>
                    </div>
                `;
            }
        });

        calendar.render();
    }
});