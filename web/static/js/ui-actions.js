(function (window) {
    const bindings = new WeakMap();
    const pendingButtons = new WeakMap();
    const timers = new Map();
    let pageVersion = 0;

    function beginPage() {
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

    window.NasToolsUI = {bindActions, args, pageAction, withButton, pageTimeout, pageInterval, beginPage,
        get pageVersion() { return pageVersion; }};
})(window);
