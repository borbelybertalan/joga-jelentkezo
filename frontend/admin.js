document.addEventListener('DOMContentLoaded', async function() {
    const addClassBtn = document.getElementById('add-class-btn');
    const classesList = document.getElementById('classes-list');

    // --- 1. ÚJ ÓRA LÉTREHOZÁSA ---
    addClassBtn.addEventListener('click', async () => {
        const title = document.getElementById('new-title').value.trim();
        const time = document.getElementById('new-time').value;
        const capacity = parseInt(document.getElementById('new-capacity').value);

        if (!title || !time || !capacity) {
            alert('Kérlek, minden mezőt tölts ki!');
            return;
        }

        // A datetime-local formátumának konvertálása a backend számára (ISO formátum)
        const isoTime = new Date(time).toISOString();

        const response = await fetch('http://127.0.0.1:8000/classes/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                start_time: isoTime,
                max_capacity: capacity
            })
        });

        if (response.ok) {
            alert('Sikeresen meghirdetted az órát!');
            location.reload(); // Oldal frissítése a lista újratöltéséhez
        } else {
            alert('Hiba történt az óra létrehozásakor.');
        }
    });

    // --- 2. ÓRÁK ÉS JELENTKEZŐK LISTÁZÁSA ---
    async function loadClasses() {
        try {
            // Lekérjük az összes órát
            const classesResponse = await fetch('http://127.0.0.1:8000/classes/');
            const classes = await classesResponse.json();
            
            classesList.innerHTML = ''; // Lista törlése

            if (classes.length === 0) {
                classesList.innerHTML = '<p>Még nincs meghirdetve egyetlen óra sem.</p>';
                return;
            }

            // Végigmegyünk az órákon
            for (const yogaClass of classes) {
                // Lekérjük az adott órához tartozó jelentkezőket
                const bookingsResponse = await fetch(`http://127.0.0.1:8000/classes/${yogaClass.id}/bookings/`);
                const bookings = await bookingsResponse.json();

                // Formatáljuk a dátumot magyarra
                const dateObj = new Date(yogaClass.start_time);
                const formattedDate = dateObj.toLocaleString('hu-HU', { 
                    year: 'numeric', month: 'long', day: 'numeric', 
                    hour: '2-digit', minute:'2-digit' 
                });

                // Létrehozzuk a HTML elemet az órának
                const classDiv = document.createElement('div');
                classDiv.className = 'class-item';
                
                // Generáljuk a résztvevők listáját (vagy kiírjuk, hogy még nincs jelentkező)
                let studentsHtml = '<ul>';
                if (bookings.length > 0) {
                    bookings.forEach(b => {
                        studentsHtml += `<li>${b.name} (${b.email})</li>`;
                    });
                } else {
                    studentsHtml += '<li><i>Még nincs jelentkező.</i></li>';
                }
                studentsHtml += '</ul>';

                classDiv.innerHTML = `
                    <h3 style="margin-bottom: 5px; color: var(--text-main);">${yogaClass.title}</h3>
                    <p style="margin-top: 0; font-size: 0.9em; color: var(--accent-color);">
                        <strong>${formattedDate}</strong> | Szabad helyek: ${yogaClass.free_spots}
                    </p>
                    ${studentsHtml}
                `;
                
                classesList.appendChild(classDiv);
            }
        } catch (error) {
            console.error(error);
            classesList.innerHTML = '<p style="color: red;">Hiba történt az adatok betöltésekor.</p>';
        }
    }

    // Függvény meghívása oldalbetöltéskor
    loadClasses();
});