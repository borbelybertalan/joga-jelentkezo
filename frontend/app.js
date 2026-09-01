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
        if (e.target === modal) {
            closeModal();
        }
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

        const bookingResponse = await fetch('http://127.0.0.1:8000/bookings/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: userName,
                email: userEmail,
                class_id: currentSelectedClassId
            })
        });

        if (bookingResponse.ok) {
            const data = await bookingResponse.json();
            alert(data.message);
            location.reload();
        } else {
            const data = await bookingResponse.json();
            alert('Hiba történt: ' + data.detail);
            submitBtn.disabled = false;
            submitBtn.textContent = 'Jelentkezem';
        }
    });

    const response = await fetch('http://127.0.0.1:8000/classes/');
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

        if (yogaClass.end_time) {
            event.end = yogaClass.end_time;
        }

        return event;
    });

    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'timeGridWeek',
        locale: 'hu',
        slotMinTime: '06:00:00',
        slotMaxTime: '22:00:00',
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },
        events: events,
        eventClick: function(info) {
            currentSelectedClassId = parseInt(info.event.id);

            modalTitle.textContent = `Jelentkezés: ${info.event.title}`;

            const start = info.event.start;
            const end = info.event.end;
            if (start) {
                const dateText = start.toLocaleDateString('hu-HU', {
                    year: 'numeric', month: 'long', day: 'numeric'
                });
                const startText = start.toLocaleTimeString('hu-HU', {
                    hour: '2-digit', minute: '2-digit'
                });
                const endText = end ? end.toLocaleTimeString('hu-HU', {
                    hour: '2-digit', minute: '2-digit'
                }) : '';
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