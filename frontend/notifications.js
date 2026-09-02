(function () {
    let resolveDialog = null;
    let lastFocusedElement = null;

    function ensureDialog() {
        let overlay = document.getElementById('app-dialog-overlay');
        if (overlay) return overlay;

        overlay = document.createElement('div');
        overlay.id = 'app-dialog-overlay';
        overlay.className = 'app-dialog-overlay';
        overlay.innerHTML = [
            '<section class="app-dialog" role="dialog" aria-modal="true" aria-labelledby="app-dialog-title" aria-describedby="app-dialog-message">',
            '<h2 id="app-dialog-title"></h2>',
            '<p id="app-dialog-message" class="app-dialog-message"></p>',
            '<div class="app-dialog-actions">',
            '<button id="app-dialog-cancel" class="btn-secondary" type="button">Mégsem</button>',
            '<button id="app-dialog-confirm" class="btn-primary" type="button">Rendben</button>',
            '</div>',
            '</section>'
        ].join('');
        document.body.append(overlay);

        overlay.addEventListener('click', event => {
            if (event.target === overlay) closeDialog(false);
        });
        overlay.querySelector('#app-dialog-cancel').addEventListener('click', () => closeDialog(false));
        overlay.querySelector('#app-dialog-confirm').addEventListener('click', () => closeDialog(true));
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && overlay.classList.contains('active')) {
                event.preventDefault();
                closeDialog(false);
            }
        });
        return overlay;
    }

    function closeDialog(result) {
        const overlay = document.getElementById('app-dialog-overlay');
        if (!overlay || !overlay.classList.contains('active')) return;
        overlay.classList.remove('active');
        document.body.classList.remove('app-dialog-open');
        if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
            lastFocusedElement.focus();
        }
        const resolve = resolveDialog;
        resolveDialog = null;
        lastFocusedElement = null;
        if (resolve) resolve(result);
    }

    function openDialog({ title, message, confirmLabel = 'Rendben', cancelLabel = 'Mégsem', needsConfirmation = false, variant = 'default' }) {
        const overlay = ensureDialog();
        const titleElement = overlay.querySelector('#app-dialog-title');
        const messageElement = overlay.querySelector('#app-dialog-message');
        const confirmButton = overlay.querySelector('#app-dialog-confirm');
        const cancelButton = overlay.querySelector('#app-dialog-cancel');

        lastFocusedElement = document.activeElement;
        titleElement.textContent = title;
        messageElement.textContent = message;
        confirmButton.textContent = confirmLabel;
        cancelButton.textContent = cancelLabel;
        cancelButton.hidden = !needsConfirmation;
        confirmButton.classList.toggle('app-dialog-danger', variant === 'danger');
        overlay.classList.remove('app-dialog-default', 'app-dialog-success', 'app-dialog-error', 'app-dialog-danger');
        overlay.classList.add(`app-dialog-${variant}`);
        overlay.classList.add('active');
        document.body.classList.add('app-dialog-open');
        window.setTimeout(() => confirmButton.focus(), 0);

        return new Promise(resolve => {
            resolveDialog = resolve;
        });
    }

    window.appDialog = {
        alert(message, options = {}) {
            return openDialog({
                title: options.title || 'Tájékoztatás',
                message,
                confirmLabel: options.confirmLabel || 'Rendben',
                variant: options.variant || 'default'
            });
        },
        confirm(message, options = {}) {
            return openDialog({
                title: options.title || 'Megerősítés',
                message,
                confirmLabel: options.confirmLabel || 'Igen, folytatom',
                cancelLabel: options.cancelLabel || 'Mégsem',
                needsConfirmation: true,
                variant: options.variant || 'default'
            });
        }
    };
}());
