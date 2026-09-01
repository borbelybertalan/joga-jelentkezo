document.addEventListener('DOMContentLoaded', () => {
    const loginScreen = document.getElementById('login-screen');
    const appContent = document.getElementById('app-content');
    const loginError = document.getElementById('login-error');
    let authToken = '';

    function showLogin() {
        authToken = '';
        sessionStorage.removeItem('jogaAdminToken');
        appContent.style.display = 'none';
        loginScreen.style.display = 'flex';
    }

    async function fetchAdmin(url, options = {}) {
        const headers = new Headers(options.headers || {});
        headers.set('Authorization', `Bearer ${authToken}`);
        const response = await fetch(url, { ...options, headers });
        if (response.status === 401) {
            showLogin();
            throw new Error('A munkamenet lejárt. Jelentkezz be újra.');
        }
        return response;
    }

    async function initializeApp(token) {
        authToken = token;
        try {
            const response = await fetchAdmin('/admin/verify');
            if (!response.ok) throw new Error('A belépés nem ellenőrizhető.');
            loginScreen.style.display = 'none';
            appContent.style.display = 'block';
            await loadCalendar();
        } catch (error) {
            showLogin();
            loginError.textContent = error.message;
            loginError.style.display = 'block';
        }
    }

    const storedToken = sessionStorage.getItem('jogaAdminToken');
    if (storedToken) initializeApp(storedToken);

    document.getElementById('login-btn').addEventListener('click', async () => {
        const user = document.getElementById('login-user').value.trim();
        const pass = document.getElementById('login-pass').value;
        if (!user || !pass) return;

        const loginButton = document.getElementById('login-btn');
        loginButton.disabled = true;
        loginError.style.display = 'none';
        try {
            const response = await fetch('/admin/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, password: pass })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'A belépés nem sikerült.');
            sessionStorage.setItem('jogaAdminToken', data.access_token);
            await initializeApp(data.access_token);
        } catch (error) {
            loginError.textContent = error.message;
            loginError.style.display = 'block';
        } finally {
            loginButton.disabled = false;
        }
    });

    document.getElementById('logout-btn').addEventListener('click', showLogin);

    function createStudentSection(title, bookings, emptyText, color, onRemove) {
        const section = document.createElement('div');
        section.style.marginBottom = '15px';
        const heading = document.createElement('strong');
        heading.textContent = title;
        section.append(heading);

        const list = document.createElement('ul');
        list.className = 'admin-student-list';
        list.style.color = color;
        if (!bookings.length) {
            const empty = document.createElement('li');
            const italic = document.createElement('i');
            italic.textContent = emptyText;
            empty.append(italic);
            list.append(empty);
        }

        bookings.forEach(booking => {
            const item = document.createElement('li');
            const identity = document.createElement('span');
            identity.textContent = `${booking.name} (${booking.email})`;
            const removeButton = document.createElement('button');
            removeButton.type = 'button';
            removeButton.className = 'btn-delete-small';
            removeButton.textContent = 'Törlés';
            removeButton.addEventListener('click', () => onRemove(booking.id));
            item.append(identity, removeButton);
            list.append(item);
        });
        section.append(list);
        return section;
    }

    async function loadCalendar() {
        const calendarEl = document.getElementById('calendar');
        const addModal = document.getElementById('add-class-modal');
        const manageModal = document.getElementById('manage-class-modal');
        const manageTitle = document.getElementById('manage-title');
        const manageTime = document.getElementById('manage-time');
        const manageInfo = document.getElementById('manage-info');
        const studentsContainer = document.getElementById('manage-students-container');
        let currentManageClassId = null;

        document.getElementById('open-add-modal-btn').addEventListener('click', () => addModal.classList.add('active'));
        document.getElementById('cancel-add-btn').addEventListener('click', () => addModal.classList.remove('active'));
        document.getElementById('close-manage-btn').addEventListener('click', () => manageModal.classList.remove('active'));

        document.getElementById('submit-add-btn').addEventListener('click', async () => {
            const title = document.getElementById('new-title').value.trim();
            const time = document.getElementById('new-time').value;
            const capacity = Number.parseInt(document.getElementById('new-capacity').value, 10);
            const instructor = document.getElementById('new-instructor').value.trim() || null;
            const note = document.getElementById('new-note').value.trim() || null;
            const zoomAvailable = document.getElementById('new-zoom').checked;
            if (!title || !time || !Number.isInteger(capacity) || capacity < 1) {
                alert('Adj meg nevet, időpontot és legalább 1 fős létszámot.');
                return;
            }

            try {
                const response = await fetchAdmin('/classes/', {
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
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'Az óra nem hozható létre.');
                location.reload();
            } catch (error) {
                alert(`Hiba történt: ${error.message}`);
            }
        });

        document.getElementById('delete-class-btn').addEventListener('click', async () => {
            if (!currentManageClassId || !confirm('Biztosan törlöd a teljes órát és minden foglalást?')) return;
            try {
                const response = await fetchAdmin(`/admin/classes/${currentManageClassId}`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'Az óra nem törölhető.');
                location.reload();
            } catch (error) {
                alert(`Hiba történt: ${error.message}`);
            }
        });

        async function removeStudent(bookingId) {
            if (!confirm('Biztosan eltávolítod a tanítványt?')) return;
            try {
                const response = await fetchAdmin(`/admin/bookings/${bookingId}`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'A tanítvány nem távolítható el.');
                location.reload();
            } catch (error) {
                alert(`Hiba történt: ${error.message}`);
            }
        }

        let classes;
        try {
            const response = await fetchAdmin('/classes/');
            if (!response.ok) throw new Error('Az órarend nem tölthető be.');
            classes = await response.json();
        } catch (error) {
            calendarEl.textContent = `Az órarend betöltése nem sikerült: ${error.message}`;
            return;
        }

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
            if (yogaClass.end_time) event.end = yogaClass.end_time;
            const title = yogaClass.title.toLowerCase();
            if (title.includes('légzés')) event.classNames = ['breathing-event'];
            if (title.includes('aktív mozgás')) {
                event.classNames = [...(event.classNames || []), 'long-title-event'];
            }
            return event;
        });

        const calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'timeGridWeek',
            locale: 'hu',
            slotMinTime: '06:00:00',
            slotMaxTime: '22:00:00',
            headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek' },
            events,
            eventClick: async info => {
                currentManageClassId = Number.parseInt(info.event.id, 10);
                const props = info.event.extendedProps;
                manageTitle.textContent = info.event.title;
                const start = info.event.start;
                const end = info.event.end;
                const dateText = start.toLocaleDateString('hu-HU', { year: 'numeric', month: 'long', day: 'numeric' });
                const startText = start.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' });
                const endText = end ? end.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' }) : '';
                manageTime.textContent = `${dateText} • ${startText}${endText ? ` - ${endText}` : ''}`;

                manageInfo.replaceChildren();
                const infoBox = document.createElement('div');
                infoBox.className = 'admin-class-info';
                const availability = document.createElement('strong');
                availability.textContent = `${props.freeSpots} szabad hely`;
                infoBox.append(availability);
                if (props.instructor) {
                    const instructor = document.createElement('div');
                    instructor.className = 'class-instructor';
                    instructor.textContent = props.instructor;
                    infoBox.append(instructor);
                }
                if (props.note) {
                    const note = document.createElement('div');
                    note.className = 'class-note';
                    note.textContent = props.note;
                    infoBox.append(note);
                }
                if (props.zoomAvailable) {
                    const zoom = document.createElement('div');
                    zoom.className = 'class-zoom';
                    zoom.textContent = 'Zoom-on is';
                    infoBox.append(zoom);
                }
                manageInfo.append(infoBox);

                studentsContainer.replaceChildren(document.createTextNode('Betöltés...'));
                manageModal.classList.add('active');
                try {
                    const response = await fetchAdmin(`/classes/${currentManageClassId}/bookings/`);
                    const bookings = await response.json().catch(() => []);
                    if (!response.ok) throw new Error('A jelentkezők nem tölthetők be.');
                    studentsContainer.replaceChildren(
                        createStudentSection('Aktív résztvevők:', bookings.filter(b => b.status === 'active'), 'Nincs aktív jelentkező.', '#2e7d32', removeStudent),
                        createStudentSection('Várólista:', bookings.filter(b => b.status === 'waitlisted'), 'Üres a várólista.', '#ef6c00', removeStudent)
                    );
                } catch (error) {
                    studentsContainer.textContent = `Hiba történt: ${error.message}`;
                }
            }
        });

        calendar.render();
    }
});
