document.addEventListener('DOMContentLoaded', () => {
    const loginScreen = document.getElementById('login-screen');
    const appContent = document.getElementById('app-content');
    const loginError = document.getElementById('login-error');
    const registry = document.getElementById('student-registry-list');
    const guestSearch = document.getElementById('guest-search');
    const guestEditorModal = document.getElementById('guest-editor-modal');
    const loginSessionNotice = document.getElementById('login-session-notice');
    const adminSessionStatus = document.getElementById('admin-session-status');
    let authToken = '';
    let registryUsers = [];
    let selectedGuestId = null;
    let sessionExpiryTimer = null;

    function sessionExpiryFromToken(token) {
        try {
            const encodedPayload = token.split('.')[0];
            const base64 = encodedPayload.replace(/-/g, '+').replace(/_/g, '/');
            const payload = JSON.parse(atob(base64));
            return Number.isFinite(payload.exp) ? payload.exp : null;
        } catch {
            return null;
        }
    }

    function setSessionStatus(expiresAt) {
        clearTimeout(sessionExpiryTimer);
        if (!expiresAt) {
            adminSessionStatus.textContent = 'Bejelentkezve.';
            return true;
        }

        const expiryDate = new Date(expiresAt * 1000);
        adminSessionStatus.textContent = `Bejelentkezve. A munkamenet ${expiryDate.toLocaleString('hu-HU')} után lejár.`;
        const remainingMilliseconds = expiryDate.getTime() - Date.now();
        if (remainingMilliseconds <= 0) {
            showLogin('A munkamenet lejárt. Jelentkezz be újra a folytatáshoz.');
            return false;
        }
        sessionExpiryTimer = window.setTimeout(() => {
            showLogin('A munkamenet lejárt. Jelentkezz be újra a folytatáshoz.');
        }, remainingMilliseconds);
        return true;
    }

    function showLogin(message = '') {
        clearTimeout(sessionExpiryTimer);
        authToken = '';
        sessionStorage.removeItem('jogaAdminToken');
        sessionStorage.removeItem('jogaAdminExpiresAt');
        guestEditorModal.classList.remove('active');
        document.body.classList.remove('guest-editor-open');
        selectedGuestId = null;
        appContent.style.display = 'none';
        loginScreen.style.display = 'flex';
        adminSessionStatus.textContent = '';
        loginError.style.display = 'none';
        loginSessionNotice.textContent = message;
        loginSessionNotice.style.display = message ? 'block' : 'none';
    }

    async function fetchAdmin(url, options = {}) {
        const headers = new Headers(options.headers || {});
        headers.set('Authorization', `Bearer ${authToken}`);
        const response = await fetch(url, { ...options, headers });
        if (response.status === 401) {
            const error = new Error('A munkamenet lejárt. Jelentkezz be újra a folytatáshoz.');
            error.sessionExpired = true;
            showLogin(error.message);
            throw error;
        }
        return response;
    }

    async function initializeApp(token, expiresAt = sessionExpiryFromToken(token), announceLogin = false) {
        authToken = token;
        try {
            const response = await fetchAdmin('/admin/verify');
            if (!response.ok) throw new Error('A belépés nem ellenőrizhető.');
            loginScreen.style.display = 'none';
            appContent.style.display = 'block';
            loginSessionNotice.style.display = 'none';
            if (!setSessionStatus(expiresAt)) return;
            await loadCalendar();
            await loadStudentRegistry();
            if (announceLogin) appDialog.toast('Sikeres belépés.', { variant: 'success' });
        } catch (error) {
            showLogin(error.message);
        }
    }

    const storedToken = sessionStorage.getItem('jogaAdminToken');
    const storedExpiry = Number.parseInt(sessionStorage.getItem('jogaAdminExpiresAt'), 10);
    if (storedToken) initializeApp(storedToken, Number.isFinite(storedExpiry) ? storedExpiry : undefined);

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
            sessionStorage.setItem('jogaAdminExpiresAt', String(data.expires_at));
            await initializeApp(data.access_token, data.expires_at, true);
        } catch (error) {
            loginError.textContent = error.message;
            loginError.style.display = 'block';
        } finally {
            loginButton.disabled = false;
        }
    });

    document.getElementById('logout-btn').addEventListener('click', () => {
        showLogin('Sikeresen kijelentkeztél. A folytatáshoz jelentkezz be újra.');
        appDialog.toast('Sikeresen kijelentkeztél.', { variant: 'info' });
    });

    function formatPass(pass) {
        if (!pass) return 'Nincs aktív bérlet';
        const type = pass.type === 'monthly' ? 'Havi bérlet' : '8 alkalmas bérlet';
        const validUntil = new Date(pass.valid_until).toLocaleDateString('hu-HU');
        const uses = pass.type === 'eight_visit' ? ` · ${pass.remaining_uses} alkalom maradt` : '';
        return `${type} · érvényes: ${validUntil}${uses}`;
    }

    async function grantPass(userId, passType) {
        const typeText = passType === 'monthly' ? 'havi' : '8 alkalmas';
        const confirmed = await appDialog.confirm(`Biztosan hozzáadod a ${typeText} bérletet?`, {
            title: 'Bérlet kiadása',
            confirmLabel: 'Bérlet hozzáadása'
        });
        if (!confirmed) return;
        try {
            const response = await fetchAdmin(`/admin/users/${userId}/passes/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pass_type: passType })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'A bérlet nem adható hozzá.');
            await refreshSelectedGuest();
            appDialog.toast(`A ${typeText} bérlet sikeresen hozzáadva.`, { variant: 'success' });
        } catch (error) {
            if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                title: 'Bérlet kiadása sikertelen',
                variant: 'error'
            });
        }
    }

    function renderStudentRegistry() {
        const searchText = guestSearch.value.trim().toLocaleLowerCase('hu-HU');
        const matchingUsers = registryUsers.filter(user =>
            user.name.toLocaleLowerCase('hu-HU').includes(searchText)
        );

        registry.replaceChildren();
        if (!matchingUsers.length) {
            registry.textContent = searchText
                ? 'Nem található ilyen nevű vendég.'
                : 'Még nincs korábban jelentkezett vendég.';
            return;
        }

        matchingUsers.forEach(user => {
            const card = document.createElement('article');
            card.className = 'student-card';

            const header = document.createElement('div');
            header.className = 'student-card-header';
            const details = document.createElement('div');
            const name = document.createElement('button');
            name.type = 'button';
            name.className = 'guest-name-button';
            name.textContent = user.name;
            name.setAttribute('aria-label', `${user.name} szerkesztése`);
            name.addEventListener('click', () => openGuestEditor(user.id));
            const emails = document.createElement('div');
            emails.className = 'student-emails';
            emails.textContent = user.emails.join(' · ');
            const pass = document.createElement('div');
            pass.className = 'student-pass';
            pass.textContent = formatPass(user.active_pass);
            details.append(name, emails, pass);
            header.append(details);
            card.append(header);
            registry.append(card);
        });
    }

    async function loadStudentRegistry() {
        registry.textContent = 'Vendégek betöltése...';
        try {
            const response = await fetchAdmin('/admin/users/');
            const users = await response.json().catch(() => []);
            if (!response.ok) throw new Error('A vendéglista nem tölthető be.');
            registryUsers = users;
            renderStudentRegistry();
        } catch (error) {
            registry.textContent = `Hiba történt: ${error.message}`;
        }
    }

    function formatDateInput(value) {
        return value ? value.slice(0, 10) : '';
    }

    function openGuestEditor(userId) {
        const guest = registryUsers.find(user => user.id === userId);
        if (!guest) return;

        selectedGuestId = guest.id;
        document.getElementById('guest-editor-title').textContent = `${guest.name} szerkesztése`;
        document.getElementById('guest-editor-emails').textContent = guest.emails.join(' · ');
        document.getElementById('guest-merge-primary-email').value = guest.emails[0];
        document.getElementById('guest-merge-secondary-email').value = '';

        const passList = document.getElementById('guest-pass-list');
        passList.replaceChildren();
        const addMonthlyButton = document.getElementById('add-monthly-pass-btn');
        const addEightVisitButton = document.getElementById('add-eight-visit-pass-btn');
        if (!guest.active_pass) {
            passList.textContent = 'Nincs aktív bérlet.';
            addMonthlyButton.hidden = false;
            addEightVisitButton.hidden = false;
        } else {
            passList.append(createPassEditor(guest.active_pass));
            addMonthlyButton.hidden = true;
            addEightVisitButton.hidden = true;
        }
        guestEditorModal.classList.add('active');
        document.body.classList.add('guest-editor-open');
    }

    function createPassEditor(pass) {
        const editor = document.createElement('article');
        editor.className = 'guest-pass-editor';
        const title = document.createElement('h3');
        title.textContent = pass.type === 'monthly' ? 'Havi bérlet' : '8 alkalmas bérlet';
        const details = document.createElement('p');
        details.textContent = `Kiadva: ${new Date(pass.issued_at).toLocaleDateString('hu-HU')}${pass.active ? '' : ' · jelenleg nem aktív'}`;

        const validUntilGroup = document.createElement('div');
        validUntilGroup.className = 'form-group';
        const validUntilLabel = document.createElement('label');
        validUntilLabel.textContent = 'Lejárati dátum';
        const validUntil = document.createElement('input');
        validUntil.type = 'date';
        validUntil.value = formatDateInput(pass.valid_until);
        validUntil.required = true;
        validUntilGroup.append(validUntilLabel, validUntil);

        const controls = [validUntil];
        editor.append(title, details, validUntilGroup);
        if (pass.type === 'eight_visit') {
            const usesGroup = document.createElement('div');
            usesGroup.className = 'form-group';
            const usesLabel = document.createElement('label');
            usesLabel.textContent = 'Fennmaradó alkalmak';
            const uses = document.createElement('input');
            uses.type = 'number';
            uses.min = '0';
            uses.max = '8';
            uses.step = '1';
            uses.value = String(pass.remaining_uses);
            uses.required = true;
            usesGroup.append(usesLabel, uses);
            editor.append(usesGroup);
            controls.push(uses);
        }

        const saveButton = document.createElement('button');
        saveButton.type = 'button';
        saveButton.className = 'btn-primary';
        saveButton.textContent = 'Bérlet módosításának mentése';
        saveButton.addEventListener('click', async () => {
            if (!validUntil.value) {
                await appDialog.alert('Add meg a lejárati dátumot.', {
                    title: 'Hiányzó adat',
                    variant: 'error'
                });
                return;
            }
            const payload = { valid_until: validUntil.value };
            if (pass.type === 'eight_visit') {
                const uses = Number.parseInt(controls[1].value, 10);
                if (!Number.isInteger(uses) || uses < 0 || uses > 8) {
                    await appDialog.alert('A fennmaradó alkalmak száma 0 és 8 közé essen.', {
                        title: 'Érvénytelen alkalomszám',
                        variant: 'error'
                    });
                    return;
                }
                payload.remaining_uses = uses;
            }
            saveButton.disabled = true;
            try {
                const response = await fetchAdmin(`/admin/passes/${pass.id}/`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'A bérlet nem módosítható.');
                await refreshSelectedGuest();
                appDialog.toast('A bérlet adatai sikeresen mentve.', { variant: 'success' });
            } catch (error) {
                if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                    title: 'Bérlet módosítása sikertelen',
                    variant: 'error'
                });
            } finally {
                saveButton.disabled = false;
            }
        });
        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'btn-secondary';
        deleteButton.textContent = 'Bérlet eltávolítása';
        deleteButton.addEventListener('click', async () => {
            const confirmed = await appDialog.confirm(
                'Biztosan eltávolítod ezt a bérletet? A bérlethez kapcsolt foglalások ezután nem lesznek bérletesek.',
                { title: 'Bérlet eltávolítása', confirmLabel: 'Bérlet eltávolítása', variant: 'danger' }
            );
            if (!confirmed) return;
            deleteButton.disabled = true;
            try {
                const response = await fetchAdmin(`/admin/passes/${pass.id}/`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'A bérlet nem távolítható el.');
                await refreshSelectedGuest();
                appDialog.toast('A bérlet sikeresen eltávolítva.', { variant: 'success' });
            } catch (error) {
                if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                    title: 'Bérlet eltávolítása sikertelen',
                    variant: 'error'
                });
            } finally {
                deleteButton.disabled = false;
            }
        });
        const actions = document.createElement('div');
        actions.className = 'guest-editor-actions';
        actions.append(saveButton, deleteButton);
        editor.append(actions);
        return editor;
    }

    async function refreshSelectedGuest() {
        const guestId = selectedGuestId;
        await loadStudentRegistry();
        if (guestId && registryUsers.some(user => user.id === guestId)) openGuestEditor(guestId);
    }

    async function deleteSelectedGuest() {
        const guest = registryUsers.find(user => user.id === selectedGuestId);
        if (!guest) return;

        const confirmed = await appDialog.confirm(
            `Biztosan véglegesen törlöd ${guest.name} vendéget?\n\nA vendég összes e-mail-címe, bérlete és foglalási előzménye is törlődik. Ez a művelet nem vonható vissza.`,
            {
                title: 'Vendég végleges törlése',
                confirmLabel: 'Vendég végleges törlése',
                variant: 'danger'
            }
        );
        if (!confirmed) return;

        const deleteButton = document.getElementById('delete-guest-btn');
        deleteButton.disabled = true;
        try {
            const response = await fetchAdmin(`/admin/users/${guest.id}/`, { method: 'DELETE' });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'A vendég nem törölhető.');
            guestEditorModal.classList.remove('active');
            document.body.classList.remove('guest-editor-open');
            selectedGuestId = null;
            await loadStudentRegistry();
            appDialog.toast(`${guest.name} és minden hozzá tartozó adat sikeresen törölve.`, {
                variant: 'success'
            });
        } catch (error) {
            if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                title: 'Vendég törlése sikertelen',
                variant: 'error'
            });
        } finally {
            deleteButton.disabled = false;
        }
    }

    guestSearch.addEventListener('input', renderStudentRegistry);
    document.getElementById('close-guest-editor-btn').addEventListener('click', () => {
        guestEditorModal.classList.remove('active');
        document.body.classList.remove('guest-editor-open');
        selectedGuestId = null;
    });
    document.getElementById('add-monthly-pass-btn').addEventListener('click', () => {
        if (selectedGuestId) grantPass(selectedGuestId, 'monthly');
    });
    document.getElementById('add-eight-visit-pass-btn').addEventListener('click', () => {
        if (selectedGuestId) grantPass(selectedGuestId, 'eight_visit');
    });
    document.getElementById('delete-guest-btn').addEventListener('click', deleteSelectedGuest);
    document.getElementById('guest-merge-emails-btn').addEventListener('click', async () => {
        const primaryEmail = document.getElementById('guest-merge-primary-email').value.trim();
        const secondaryInput = document.getElementById('guest-merge-secondary-email');
        const secondaryEmail = secondaryInput.value.trim();
        if (!primaryEmail || !secondaryEmail) {
            await appDialog.alert('Add meg a hozzákapcsolandó e-mail-címet.', {
                title: 'Hiányzó adat',
                variant: 'error'
            });
            return;
        }
        const confirmed = await appDialog.confirm(
            `Biztosan ehhez a vendéghez kapcsolod ezt az e-mail-címet?\n${secondaryEmail}`,
            { title: 'E-mail-címek összevonása', confirmLabel: 'E-mail-cím hozzákapcsolása' }
        );
        if (!confirmed) return;
        try {
            const response = await fetchAdmin('/admin/users/merge-emails/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ primary_email: primaryEmail, secondary_email: secondaryEmail })
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Az e-mail-címek nem vonhatók össze.');
            await refreshSelectedGuest();
            appDialog.toast(data.message, { variant: 'success' });
        } catch (error) {
            if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                title: 'E-mail-címek összevonása sikertelen',
                variant: 'error'
            });
        }
    });

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
            identity.textContent = `${booking.name} (${booking.email}) — ${formatPass(booking.pass)}`;
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
        const editModal = document.getElementById('edit-class-modal');
        const manageTitle = document.getElementById('manage-title');
        const manageTime = document.getElementById('manage-time');
        const manageInfo = document.getElementById('manage-info');
        const studentsContainer = document.getElementById('manage-students-container');
        const deleteClassButton = document.getElementById('delete-class-btn');
        const deleteClassSummary = document.getElementById('delete-class-summary');
        let currentManageClassId = null;
        let currentManageClassTitle = '';
        let currentActiveBookings = 0;
        let currentWaitlistedBookings = 0;

        function formatDateTimeLocal(date) {
            const pad = value => String(value).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
        }

        function populateEditClassForm(event) {
            const props = event.extendedProps;
            document.getElementById('edit-title').value = event.title;
            document.getElementById('edit-time').value = formatDateTimeLocal(event.start);
            document.getElementById('edit-capacity').value = String(props.maxCapacity);
            document.getElementById('edit-instructor').value = props.instructor || '';
            document.getElementById('edit-note').value = props.note || '';
            document.getElementById('edit-zoom').checked = Boolean(props.zoomAvailable);
        }

        function updateDeleteSummary() {
            const total = currentActiveBookings + currentWaitlistedBookings;
            deleteClassSummary.textContent = `${total} érintett: ${currentActiveBookings} aktív jelentkező és ${currentWaitlistedBookings} várólistás. A törlés az órát és minden kapcsolódó foglalást végleg eltávolítja.`;
            deleteClassButton.textContent = `Óra törlése (${total})`;
            deleteClassButton.disabled = false;
        }

        document.getElementById('open-add-modal-btn').addEventListener('click', () => addModal.classList.add('active'));
        document.getElementById('cancel-add-btn').addEventListener('click', () => addModal.classList.remove('active'));
        document.getElementById('close-manage-btn').addEventListener('click', () => manageModal.classList.remove('active'));
        document.getElementById('cancel-edit-class-btn').addEventListener('click', () => editModal.classList.remove('active'));

        document.getElementById('edit-class-btn').addEventListener('click', () => {
            if (!currentManageClassId) return;
            manageModal.classList.remove('active');
            editModal.classList.add('active');
        });

        document.getElementById('submit-add-btn').addEventListener('click', async () => {
            const title = document.getElementById('new-title').value.trim();
            const time = document.getElementById('new-time').value;
            const capacity = Number.parseInt(document.getElementById('new-capacity').value, 10);
            const instructor = document.getElementById('new-instructor').value.trim() || null;
            const note = document.getElementById('new-note').value.trim() || null;
            const zoomAvailable = document.getElementById('new-zoom').checked;
            if (!title || !time || !Number.isInteger(capacity) || capacity < 1) {
                await appDialog.alert('Adj meg nevet, időpontot és legalább 1 fős létszámot.', {
                    title: 'Hiányzó vagy érvénytelen adat',
                    variant: 'error'
                });
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
                appDialog.flashToast('Az óra sikeresen meghirdetve.', { variant: 'success' });
                location.reload();
            } catch (error) {
                if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                    title: 'Óra meghirdetése sikertelen',
                    variant: 'error'
                });
            }
        });

        document.getElementById('submit-edit-class-btn').addEventListener('click', async () => {
            const title = document.getElementById('edit-title').value.trim();
            const time = document.getElementById('edit-time').value;
            const capacity = Number.parseInt(document.getElementById('edit-capacity').value, 10);
            const instructor = document.getElementById('edit-instructor').value.trim() || null;
            const note = document.getElementById('edit-note').value.trim() || null;
            const zoomAvailable = document.getElementById('edit-zoom').checked;
            if (!currentManageClassId || !title || !time || !Number.isInteger(capacity) || capacity < 1) {
                await appDialog.alert('Adj meg nevet, időpontot és legalább 1 fős létszámot.', {
                    title: 'Hiányzó vagy érvénytelen adat',
                    variant: 'error'
                });
                return;
            }

            const saveButton = document.getElementById('submit-edit-class-btn');
            saveButton.disabled = true;
            try {
                const response = await fetchAdmin(`/admin/classes/${currentManageClassId}`, {
                    method: 'PATCH',
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
                if (!response.ok) throw new Error(data.detail || 'Az óra nem szerkeszthető.');
                appDialog.flashToast('Az óra változtatásai sikeresen mentve.', { variant: 'success' });
                location.reload();
            } catch (error) {
                if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                    title: 'Óra szerkesztése sikertelen',
                    variant: 'error'
                });
            } finally {
                saveButton.disabled = false;
            }
        });

        deleteClassButton.addEventListener('click', async () => {
            if (!currentManageClassId || deleteClassButton.disabled) return;
            const total = currentActiveBookings + currentWaitlistedBookings;
            const confirmation = [
                `Biztosan törlöd ezt az órát: ${currentManageClassTitle}?`,
                '',
                `Érintettek: ${total} fő (${currentActiveBookings} aktív jelentkező, ${currentWaitlistedBookings} várólistás).`,
                'A törlés után az óra, minden foglalás és a várólista végleg eltűnik.',
                'Az érintettek nem kapnak automatikus e-mailt. A korábban levont 8 alkalmas bérletes alkalmak visszakerülnek.'
            ].join('\n');
            const confirmed = await appDialog.confirm(confirmation, {
                title: 'Óra törlése',
                confirmLabel: 'Óra törlése',
                variant: 'danger'
            });
            if (!confirmed) return;
            try {
                const response = await fetchAdmin(`/admin/classes/${currentManageClassId}`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'Az óra nem törölhető.');
                appDialog.flashToast(`Az óra és ${total} érintett foglalás sikeresen törölve.`, { variant: 'success' });
                location.reload();
            } catch (error) {
                if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                    title: 'Óra törlése sikertelen',
                    variant: 'error'
                });
            }
        });

        async function removeStudent(bookingId) {
            const confirmed = await appDialog.confirm('Biztosan eltávolítod a tanítványt?', {
                title: 'Jelentkező eltávolítása',
                confirmLabel: 'Jelentkező eltávolítása',
                variant: 'danger'
            });
            if (!confirmed) return;
            try {
                const response = await fetchAdmin(`/admin/bookings/${bookingId}`, { method: 'DELETE' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'A tanítvány nem távolítható el.');
                appDialog.flashToast('A jelentkező sikeresen eltávolítva.', { variant: 'success' });
                location.reload();
            } catch (error) {
                if (!error.sessionExpired) await appDialog.alert(`Hiba történt: ${error.message}`, {
                    title: 'Jelentkező eltávolítása sikertelen',
                    variant: 'error'
                });
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

        const now = Date.now();
        const events = classes.map(yogaClass => {
            const event = {
                id: yogaClass.id,
                title: yogaClass.title,
                start: yogaClass.start_time,
                allDay: false,
                extendedProps: {
                    freeSpots: yogaClass.free_spots,
                    maxCapacity: yogaClass.max_capacity,
                    instructor: yogaClass.instructor,
                    note: yogaClass.note,
                    zoomAvailable: yogaClass.zoom_available
                }
            };
            if (yogaClass.end_time) event.end = yogaClass.end_time;
            if (new Date(yogaClass.start_time).getTime() <= now) event.classNames = ['past-event'];
            const title = yogaClass.title.toLowerCase();
            if (title.includes('légzés')) event.classNames = [...(event.classNames || []), 'breathing-event'];
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
                currentManageClassTitle = info.event.title;
                currentActiveBookings = 0;
                currentWaitlistedBookings = 0;
                const props = info.event.extendedProps;
                populateEditClassForm(info.event);
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
                deleteClassButton.disabled = true;
                deleteClassButton.textContent = 'Óra törlése';
                deleteClassSummary.textContent = 'A jelentkezők és a törlés következményeinek betöltése...';
                manageModal.classList.add('active');
                try {
                    const response = await fetchAdmin(`/classes/${currentManageClassId}/bookings/`);
                    const bookings = await response.json().catch(() => []);
                    if (!response.ok) throw new Error('A jelentkezők nem tölthetők be.');
                    const activeBookings = bookings.filter(booking => booking.status === 'active');
                    const waitlistedBookings = bookings.filter(booking => booking.status === 'waitlisted');
                    currentActiveBookings = activeBookings.length;
                    currentWaitlistedBookings = waitlistedBookings.length;
                    studentsContainer.replaceChildren(
                        createStudentSection('Aktív résztvevők:', activeBookings, 'Nincs aktív jelentkező.', '#2e7d32', removeStudent),
                        createStudentSection('Várólista:', waitlistedBookings, 'Üres a várólista.', '#ef6c00', removeStudent)
                    );
                    updateDeleteSummary();
                } catch (error) {
                    studentsContainer.textContent = `Hiba történt: ${error.message}`;
                    deleteClassSummary.textContent = 'A jelentkezők száma most nem tölthető be, ezért az óra törlése nem érhető el.';
                }
            }
        });

        calendar.render();
    }
});
