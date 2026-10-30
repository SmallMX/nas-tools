(function (window) {
    const bindings = new WeakMap();
    const pendingButtons = new WeakMap();
    const timers = new Map();
    const formTrackers = new Set();
    const trackedRoots = new WeakMap();
    let pageVersion = 0;

    function beginPage() {
        for (const tracker of formTrackers) tracker.dispose();
        pageVersion += 1;
        for (const [id, cancel] of timers) cancel(id);
        timers.clear();
        return pageVersion;
    }

    function bindActions(root, handlers) {
        root = typeof root === "string" ? document.querySelector(root) : root;
        if (!root) return;
        for (const [event, listener] of bindings.get(root) || []) root.removeEventListener(event, listener);
        const listeners = [];
        for (const [eventName, actions] of Object.entries(handlers)) {
            const attribute = `data-nt-${eventName}`;
            const listener = (event) => {
                const target = event.target instanceof Element ? event.target : event.target?.parentElement;
                const element = target?.closest(`[${attribute}]`);
                if (!element || !root.contains(element)) return;
                const name = element.getAttribute(attribute);
                if (!Object.prototype.hasOwnProperty.call(actions, name)) return;
                if (element.disabled || element.getAttribute("aria-disabled") === "true" || pendingButtons.has(element)) {
                    event.preventDefault();
                    return;
                }
                if (eventName === "click" && !element.matches('input[type="checkbox"], input[type="radio"]')) {
                    event.preventDefault();
                }
                actions[name](element, event);
            };
            root.addEventListener(eventName, listener);
            listeners.push([eventName, listener]);
        }
        bindings.set(root, listeners);
    }

    function args(element) {
        return JSON.parse(element.getAttribute("data-nt-args") || "[]");
    }

    // 页面只接收本次进入期间发起的响应；写请求仍由服务端正常完成。
    function pageAction(cmd, params, handler, async = true, showProgress = true) {
        const version = pageVersion;
        return ajax_post(cmd, params, (response) => {
            if (version === pageVersion) handler?.(response);
        }, async, showProgress);
    }

    function withButton(button, busyText, operation) {
        const element = typeof button === "string" ? document.querySelector(button) : button;
        if (!element) return Promise.resolve().then(operation);
        if (pendingButtons.has(element)) return pendingButtons.get(element);
        if (element.disabled || element.getAttribute("aria-disabled") === "true") return Promise.resolve();
        const html = element.innerHTML;
        const disabled = element.getAttribute("disabled");
        const ariaDisabled = element.getAttribute("aria-disabled");
        const ariaBusy = element.getAttribute("aria-busy");
        if (busyText !== undefined && busyText !== null) element.textContent = busyText;
        element.setAttribute("disabled", "");
        element.setAttribute("aria-disabled", "true");
        element.setAttribute("aria-busy", "true");
        const restoreAttribute = (name, value) => {
            if (value === null) element.removeAttribute(name);
            else element.setAttribute(name, value);
        };
        const pending = Promise.resolve().then(operation).finally(() => {
            element.innerHTML = html;
            restoreAttribute("disabled", disabled);
            restoreAttribute("aria-disabled", ariaDisabled);
            restoreAttribute("aria-busy", ariaBusy);
            pendingButtons.delete(element);
        });
        pendingButtons.set(element, pending);
        return pending;
    }

    function pageTimeout(callback, delay, ...args) {
        const version = pageVersion;
        const id = window.setTimeout(() => {
            timers.delete(id);
            if (version === pageVersion) callback(...args);
        }, delay);
        timers.set(id, window.clearTimeout.bind(window));
        return id;
    }

    function pageInterval(callback, delay, ...args) {
        const version = pageVersion;
        const id = window.setInterval(() => {
            if (version === pageVersion) callback(...args);
        }, delay);
        timers.set(id, window.clearInterval.bind(window));
        return id;
    }

    // 快照只保留在当前页面内存中，不将密码或表单草稿写入浏览器存储。
    function trackForm(root, options = {}) {
        root = typeof root === 'string' ? document.querySelector(root) : root;
        if (!root) return null;
        trackedRoots.get(root)?.dispose();
        const label = options.label || root.getAttribute('data-unsaved-label') || '当前表单';
        root.setAttribute('data-unsaved-label', label);
        const status = typeof options.status === 'string' ? document.querySelector(options.status) : options.status;
        const read = options.read || (() => Array.from(root.querySelectorAll('input, select, textarea'))
            .filter(field => !field.hasAttribute('data-dirty-ignore') && !['button', 'submit', 'reset'].includes(field.type))
            .map((field, index) => ({
                key: field.id || `${field.name || field.type}:${index}`,
                value: field.type === 'checkbox' || field.type === 'radio' ? [field.value, field.checked]
                    : field.type === 'file' ? Array.from(field.files || [], file => [file.name, file.size, file.lastModified])
                    : field.multiple ? Array.from(field.selectedOptions, option => option.value) : field.value,
                invalid: Boolean(field.validity?.badInput)
            })));
        const capture = () => JSON.stringify(read());
        let baseline = capture();
        let saved = false;
        const isDirty = () => capture() !== baseline;
        function setStatus(message, kind = 'info') {
            if (!status) return;
            if (status.textContent !== message) status.textContent = message;
            status.dataset.saveState = kind;
            status.classList.toggle('text-danger', kind === 'error');
            status.classList.toggle('text-muted', kind !== 'error');
        }
        function refresh() {
            const dirty = isDirty();
            root.dataset.unsaved = String(dirty);
            setStatus(dirty ? '有未保存更改' : saved ? '已保存' : '未修改', dirty ? 'dirty' : 'clean');
        }
        const tracker = {
            root, label, capture, isDirty, refresh, setStatus,
            markSaved(snapshot = capture()) {
                baseline = snapshot;
                saved = true;
                refresh();
                if (isDirty()) setStatus('已保存提交的内容，仍有未保存更改', 'dirty');
            },
            dispose() {
                root.removeEventListener('input', refresh);
                root.removeEventListener('change', refresh);
                formTrackers.delete(tracker);
                trackedRoots.delete(root);
            }
        };
        root.addEventListener('input', refresh);
        root.addEventListener('change', refresh);
        trackedRoots.set(root, tracker);
        formTrackers.add(tracker);
        refresh();
        return tracker;
    }

    function dirtyForms(scope) {
        const dirty = [];
        for (const tracker of formTrackers) {
            if (!tracker.root.isConnected) {
                tracker.dispose();
            } else if ((!scope || scope === tracker.root || scope.contains(tracker.root)) && tracker.isDirty()) {
                dirty.push(tracker);
            }
        }
        return dirty;
    }

    function confirmLeave() {
        const labels = [...new Set(dirtyForms().map(tracker => tracker.label))];
        if (!labels.length) return Promise.resolve(true);
        return window.show_unsaved_dialog(`${labels.join('、')}有未保存更改。离开后这些修改将丢失。`, '放弃修改并离开');
    }

    window.addEventListener?.('beforeunload', event => {
        if (!dirtyForms().length) return;
        event.preventDefault();
        event.returnValue = '';
    });

    if (window.document && window.jQuery) {
        const origins = new WeakMap();
        const approvedHides = new WeakSet();
        const pendingHides = new WeakSet();
        let closingOrigin = null;
        const $ = window.jQuery;
        $(document).on('show.bs.modal', '.modal', function () {
            let origin = document.activeElement;
            if ((!origin || origin === document.body || origin === document.documentElement) && closingOrigin) origin = closingOrigin;
            const seen = new Set();
            let parent = origin?.closest?.('.modal');
            while (parent && origins.has(parent) && !seen.has(parent)) {
                seen.add(parent);
                origin = origins.get(parent);
                parent = origin?.closest?.('.modal');
            }
            origins.set(this, origin);
        });
        $(document).on('hide.bs.modal', '.modal', function (event) {
            closingOrigin = origins.get(this) || null;
            if (approvedHides.has(this)) {
                approvedHides.delete(this);
                return;
            }
            const labels = [...new Set(dirtyForms(this).map(tracker => tracker.label))];
            if (!labels.length) return;
            event.preventDefault();
            if (pendingHides.has(this)) return;
            pendingHides.add(this);
            window.show_unsaved_dialog(`${labels.join('、')}尚未保存。关闭后草稿只保留在当前页面，不会保存到服务器。`, '关闭并保留本页草稿')
                .then(allowed => {
                    if (allowed && this.isConnected) {
                        approvedHides.add(this);
                        window.bootstrap?.Modal?.getInstance(this)?.hide();
                    }
                }).finally(() => pendingHides.delete(this));
        });
        $(document).on('hidden.bs.modal', '.modal', function () {
            const origin = origins.get(this);
            window.requestAnimationFrame(() => {
                if (closingOrigin === origin) closingOrigin = null;
                if (document.querySelector('.modal.show, .offcanvas.show')) return;
                if (origin?.isConnected && origin !== document.body && origin !== document.documentElement
                    && !origin.disabled && origin.getClientRects().length
                    && !origin.closest('[hidden], [aria-hidden="true"]')) {
                    origin.focus({preventScroll: true});
                } else {
                    document.querySelector('#page_content')?.focus({preventScroll: true});
                }
            });
        });
    }

    window.NasToolsUI = {bindActions, args, pageAction, withButton, pageTimeout, pageInterval, beginPage,
        trackForm, dirtyForms, confirmLeave,
        get pageVersion() { return pageVersion; }};
})(window);
