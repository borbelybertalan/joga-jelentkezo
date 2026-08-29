document.addEventListener('DOMContentLoaded', async function() {
    const calendarEl = document.getElementById('calendar');
    
    // Felugró ablak elemeinek lekérése
    const modal = document.getElementById('booking-modal');
    const modalTitle = document.getElementById('modal-title');
    const nameInput = document.getElementById('user-name');
    const emailInput = document.getElementById('user-email');
    const cancelBtn = document.getElementById('cancel-btn');
    const submitBtn = document.getElementById('submit-btn');

    let currentSelectedClassId = null;

    // Ablak bezárása függvény
    function closeModal() {
        modal.classList.remove('active');
        // Kicsit várunk a tartalom törlésével, amíg lefut a bezáródás animációja
        setTimeout(() => {
            nameInput.value = '';
            emailInput.value = '';
            currentSelectedClassId = null;
        }, 300);
    }

    // Bezárás, ha a Mégsem gombra kattint
    cancelBtn.addEventListener('click', closeModal);

    // Bezárás, ha a sötét háttérre (az ablakon kívülre) kattint
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // Foglalás elküldése, ha a Jelentkezem gombra kattint
    submitBtn.addEventListener('click', async () => {
        const userName = nameInput.value.trim();
        const userEmail = emailInput.value.trim();

        if (!userName || !userEmail) {
            alert('Kérlek, tölts ki minden mezőt a jelentkezéshez!');
            return;
        }

        if (!currentSelectedClassId) return;

        // Gomb letiltása, amíg tölt
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
            // Itt beolvassuk a backend által küldött választ
            const data = await bookingResponse.json(); 
            // A hardkódolt szöveg helyett a backend üzenetét jelenítjük meg
            alert(data.message); 
            location.reload(); // Frissíti az oldalt
        } else {
            const data = await bookingResponse.json();
            alert('Hiba történt: ' + data.detail);
            submitBtn.disabled = false;
            submitBtn.textContent = 'Jelentkezem';
        }
    });

    // 1. Órák lekérése a backendtől
    const response = await fetch('http://127.0.0.1:8000/classes/');
    const classes = await response.json();

    // 2. Formázás a naptárnak, szabad helyek kijelzésével
    const events = classes.map(yogaClass => ({
        id: yogaClass.id,
        title: `${yogaClass.title} (${yogaClass.free_spots} szabad)`,
        start: yogaClass.start_time,
        allDay: false
    }));

    // 3. Naptár rajzolása és foglalás logika
    var calendar = new FullCalendar.Calendar(calendarEl, {
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
            // Felugró ablak megnyitása és adatok betöltése
            currentSelectedClassId = parseInt(info.event.id);
            
            // Kiszűrjük a "(X szabad)" részt, hogy csak az óra neve jelenjen meg a címben
            const classTitle = info.event.title.split(' (')[0];
            modalTitle.textContent = `Jelentkezés: ${classTitle}`;
            
            modal.classList.add('active'); // Ez jeleníti meg az ablakot
        }
    });

    calendar.render();
});