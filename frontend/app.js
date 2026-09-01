document.addEventListener('DOMContentLoaded', async function() {
    const calendarEl = document.getElementById('calendar');

    const modal = document.getElementById('booking-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalTime = document.getElementById('modal-time');
    const modalFreeSpots = document.getElementById('modal-free-spots');
    const modalInstructor = document.getElementById('modal-instructor');
    const modalNote = document.getElementById('modal-note');
    const modalZoom = document.getElementById('modal-zoom');
    const nameInput = document.getElementById('user-name');
    const emailInput = document.getElementById('user-email');
    const cancelBtn = document.getElementById('cancel-btn');
    const submitBtn = document.getElementById('submit-btn');

    let currentSelectedClassId = null;

    function closeModal() {
        modal.classList.remove('active');
        setTimeout(() => {
            nameInput.value = '';
            emailInput.value = '';
            currentSelectedClassId = null;
        }, 300);
    }

    cancelBtn.addEventListener('click', closeModal);

    window.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    submitBtn.addEventListener('click', async () => {
        const userName = nameInput.value.trim();
        const userEmail = emailInput.value.trim();
        if (!userName || !userEmail) {
            alert('Kérlek, tölts ki minden mezőt a jelentkezéshez!');
            return;
        }
        if (!currentSelectedClassId) return;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Jelentkezés...';

        try {
            const bookingResponse = await fetch('/bookings/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: userName, email: userEmail, class_id: currentSelectedClassId })
            });
            const data = await bookingResponse.json().catch(() => ({}));

            if (!bookingResponse.ok) {
                throw new Error(data.detail || 'A jelentkezés nem sikerült.');
            }

            const cancellationNote = data.cancel_url
                ? `\n\nLemondó link (őrizd meg az e-mailes visszaigazolásig):\n${data.cancel_url}`
                : '';
            alert(data.message + cancellationNote);
            location.reload();
        } catch (error) {
            alert('Hiba történt: ' + error.message);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Jelentkezem';
        }
    });

    let classes;
    try {
        const response = await fetch('/classes/');
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
        // A hosszabb című órát a CSS az eredeti dobozmagasságon belül igazítja.
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
        headerToolbar: { left: 'prev,next today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay' },
        events: events,
        eventClick: function(info) {
            currentSelectedClassId = parseInt(info.event.id);
            modalTitle.textContent = `Jelentkezés: ${info.event.title}`;

            const start = info.event.start;
            const end = info.event.end;
            if (start) {
                const dateText = start.toLocaleDateString('hu-HU', { year: 'numeric', month: 'long', day: 'numeric' });
                const startText = start.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' });
                const endText = end ? end.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' }) : '';
                modalTime.textContent = `${dateText} • ${startText}${endText ? ` - ${endText}` : ''}`;
            } else {
                modalTime.textContent = '';
            }

            modalFreeSpots.textContent = `${info.event.extendedProps.freeSpots} szabad hely`;

            const instructor = info.event.extendedProps.instructor;
            modalInstructor.textContent = instructor || '';
            modalInstructor.style.display = instructor ? 'block' : 'none';

            const note = info.event.extendedProps.note;
            modalNote.textContent = note || '';
            modalNote.style.display = note ? 'block' : 'none';

            const zoomAvailable = info.event.extendedProps.zoomAvailable;
            modalZoom.textContent = zoomAvailable ? 'Zoom-on is' : '';
            modalZoom.style.display = zoomAvailable ? 'block' : 'none';

            modal.classList.add('active');
        }
    });

    calendar.render();
});
