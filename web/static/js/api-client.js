(function (window) {
    class ApiClientError extends Error {
        constructor(message, status = 0, cause = null) {
            super(message);
            this.name = "ApiClientError";
            this.status = status;
            this.cause = cause;
        }
    }

    async function postAction(cmd, params = {}, options = {}) {
        const {
            timeoutMs = 120000,
            showProgress = true,
            signal = null,
        } = options;
        const controller = new AbortController();
        let timedOut = false;
        const timeout = window.setTimeout(() => {
            timedOut = true;
            controller.abort();
        }, timeoutMs);
        const abortRequest = () => controller.abort();
        signal?.addEventListener("abort", abortRequest, {once: true});

        if (showProgress) NProgress.start();
        try {
            const body = new URLSearchParams({
                cmd,
                data: JSON.stringify(params ?? {}),
            });
            const response = await fetch(`/do?random=${Math.random()}`, {
                method: "POST",
                body,
                credentials: "same-origin",
                headers: {"Accept": "application/json"},
                signal: controller.signal,
            });
            if (response.status === 401) {
                window.dispatchEvent(new CustomEvent("nastool:auth-expired"));
            }
            const contentType = response.headers.get("Content-Type") || "";
            if (!contentType.includes("application/json")) {
                if (response.redirected) {
                    window.dispatchEvent(new CustomEvent("nastool:auth-expired"));
                    throw new ApiClientError("登录状态已失效，请重新登录", response.status);
                }
                throw new ApiClientError("服务器返回了无法识别的响应", response.status);
            }
            const payload = await response.json();
            if (!response.ok) {
                const message = response.status === 401
                    ? "登录状态已失效，请重新登录"
                    : payload.msg || payload.message || `请求失败（${response.status}）`;
                throw new ApiClientError(message, response.status);
            }
            return payload;
        } catch (error) {
            if (error instanceof ApiClientError) throw error;
            if (error.name === "AbortError") {
                const message = timedOut ? "请求超时，请稍后重试" : "请求已取消";
                throw new ApiClientError(message, 0, error);
            }
            throw new ApiClientError("网络连接异常，请检查服务状态", 0, error);
        } finally {
            window.clearTimeout(timeout);
            signal?.removeEventListener("abort", abortRequest);
            if (showProgress) NProgress.done();
        }
    }

    window.addEventListener("nastool:auth-expired", () => {
        window.location.assign("/");
    });
    window.NasToolsApi = {ApiClientError, postAction};
})(window);
