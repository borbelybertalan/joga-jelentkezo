(function () {
    let resolveDialog = null;
    let lastFocusedElement = null;
    const FLASH_TOAST_KEY = 'jogaFlashToast';

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

    function ensureToastContainer() {
        let container = document.getElementById('app-toast-container');
        if (container) return container;
        container = document.createElement('div');
        container.id = 'app-toast-container';
        container.className = 'app-toast-container';
        container.setAttribute('aria-live', 'polite');
        container.setAttribute('aria-atomic', 'true');
        document.body.append(container);
        return container;
    }

    function toast(message, options = {}) {
        const container = ensureToastContainer();
        const notification = document.createElement('div');
        const variant = options.variant || 'success';
        notification.className = `app-toast app-toast-${variant}`;
        notification.setAttribute('role', 'status');

        const text = document.createElement('span');
        text.className = 'app-toast-message';
        text.textContent = message;
        notification.append(text);

        if (options.actionLabel && options.actionHref) {
            const action = document.createElement('a');
            action.className = 'app-toast-action';
            action.textContent = options.actionLabel;
            action.href = options.actionHref;
            notification.append(action);
        }

        container.append(notification);
        window.setTimeout(() => notification.classList.add('is-leaving'), 3000);
        window.setTimeout(() => notification.remove(), 3400);
    }

    function flashToast(message, options = {}) {
        sessionStorage.setItem(FLASH_TOAST_KEY, JSON.stringify({ message, options }));
    }

    function restoreFlashToast() {
        try {
            const flash = JSON.parse(sessionStorage.getItem(FLASH_TOAST_KEY));
            if (!flash || typeof flash.message !== 'string') return;
            sessionStorage.removeItem(FLASH_TOAST_KEY);
            toast(flash.message, flash.options || {});
        } catch {
            sessionStorage.removeItem(FLASH_TOAST_KEY);
        }
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
        },
        toast,
        flashToast
    };

    restoreFlashToast();
}());
