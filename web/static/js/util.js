
// 进度条配置
NProgress.configure({ showSpinner: false });

// 兼容现有回调式调用，内部统一使用可超时、可取消的请求客户端。
function ajax_post(cmd, params, handler, aync=true, show_progress=true) {
    if (!aync) {
        throw new Error("同步请求已停止支持，请改用异步回调或 NasToolsApi.postAction");
    }
    return window.NasToolsApi.postAction(cmd, params, {showProgress: show_progress}).then((data) => {
        handler?.(data);
        return data;
    }).catch((error) => {
        const failure = {code: -99, msg: error.message || "网络错误"};
        handler?.(failure);
        return failure;
    });
}

// 备份文件下载
function ajax_backup(handler) {
    const downloadURL = "/backup";
    let xhr = new XMLHttpRequest()
    xhr.open('POST', downloadURL, true);
    xhr.responseType = 'arraybuffer';
    xhr.onload = function () {
        if (this.status === 401) {
            window.dispatchEvent(new CustomEvent("nastool:auth-expired"));
        }
        if (this.status === 200) {
            let type = xhr.getResponseHeader('Content-Type')
            let fileName = xhr.getResponseHeader('Content-Disposition')
                .split(';')[1]
                .split('=')[1]
                .replace(/\"/g, '')

            let blob = new Blob([this.response], {type: type})
            if (typeof window.navigator.msSaveBlob !== 'undefined') {
                /*
                 * IE workaround for "HTML7007: One or more blob URLs were revoked by closing
                 * the blob for which they were created. These URLs will no longer resolve as
                 * the data backing the URL has been freed."
                 */
                window.navigator.msSaveBlob(blob, fileName);
            } else {
                let URL = window.URL || window.webkitURL;
                let objectUrl = URL.createObjectURL(blob);
                if (fileName) {
                    const a = document.createElement('a');
                    // safari doesn't support this yet
                    if (typeof a.download === 'undefined') {
                        window.location = objectUrl
                    } else {
                        a.href = objectUrl;
                        a.download = fileName;
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        URL.revokeObjectURL(objectUrl);
                    }
                } else {
                    window.location = objectUrl;
                }
            }
        }
        if (handler) {
            handler();
        }
    };
    xhr.send();
}

// 获取链接参数
function getQueryVariable(variable) {
    const query = window.location.search.substring(1);
    const vars = query.split("&");
    for (let i = 0; i < vars.length; i++) {
        const pair = vars[i].split("=");
        if (pair[0] == variable) {
            return pair[1];
        }
    }
    return false;
}

// 鼠标提示等待
function make_cursor_busy() {
    const body = document.querySelector("body");
    body.style.cursor = "wait";
}

// 鼠标取消等待
function cancel_cursor_busy() {
    const body = document.querySelector("body");
    body.style.cursor = "default";
}

// 是否触摸屏设备
function is_touch_device() {
    return 'ontouchstart' in window;
}

// replaceAll浏览器兼容
String.prototype.replaceAll = function (s1, s2) {
    return this.replace(new RegExp(s1, "gm"), s2)
}

function select_name(name) {
    if (name.startsWith("\^")) {
        return `name^=${name.substring(1)}`;
    } else {
        return `name=${name}`;
    }
}

/**
 * 全选按钮绑定
 * @param: btnobj 按钮对象
 * @param: name 被管理checkbox的name
 **/
function select_btn_SelectALL(btnobj, name) {
    if ($(btnobj).text() === "全选") {
        $(`input[${select_name(name)}][type=checkbox]`).prop("checked", true);
        $(btnobj).text("全不选");
    } else {
        $(`input[${select_name(name)}][type=checkbox]`).prop("checked", false);
        $(btnobj).text("全选");
    }
}

/**
 * 全选事件
 * @param: status 全选框状态
 * @param: name 被管理checkbox的name
 **/
function select_SelectALL(status, name) {
    $(`input[${select_name(name)}][type=checkbox]`).prop("checked", status);
}

/**
 * 部分选定事件
 * @param: status 全选框状态
 * @param: name 被管理checkbox的name
 **/
function select_SelectPart(condition, name) {
    $(`input[${select_name(name)}][type=checkbox]`).each(function () {
        if (condition && condition.includes($(this).val())) {
            $(this).prop("checked", true);
        } else {
            $(this).prop("checked", false);
        }
    });
}

/**
 * 获取选中input元素value
 * @param: name 被管理checkbox的name
 **/
function select_GetSelectedVAL(name) {
    let selectedVAL = [];
    $(`input[${select_name(name)}][type=checkbox]`).each(function () {
        if ($(this).prop("checked")) {
        selectedVAL.push($(this).val());
        }
    });
    return selectedVAL;
}

/**
 * 获取隐藏input元素value
 * @param: name 被管理checkbox的name
 **/
function select_GetHiddenVAL(name) {
    let hiddenVAL = [];
    $(`input[${select_name(name)}][type=hidden]`).each(function () {
        hiddenVAL.push($(this).val());
    });
    return hiddenVAL;
}

/**
 * 获取元素下input设置
 * @param: id 元素id
 **/
function input_select_GetVal(id, prefix=null) {
    let params = {};
    $(`#${id} input`).each(function () {
        let key = $(this).attr("id");
        if (key) {
            params[(prefix) ? key.replace(prefix, "") : key] = ($(this).attr("type") === "checkbox") ? !!$(this).prop("checked") : $(this).val();
        }
    });
    $(`#${id} select`).each(function () {
        let key = $(this).attr("id");
        if (key) {
            params[(prefix) ? key.replace(prefix, "") : key] = $(this).val();
        }
    });
    return params;
}

/**
 * 对象数组排序，针对纯英文、数字或纯中文的排序
 * @param: objArr 需要排序的对象数组
 * @param: sortKey  需要进行排序的键
 * @param: sortType asc升序(默认)  desc 降序
 **/
function dictArraySorting(objArr,sortKey,sortType="asc") {
    return objArr.sort(function (obj1, obj2) {
        let val1 = obj1[sortKey];
        let val2 = obj2[sortKey];
        if (!isNaN(Number(val1)) && !isNaN(Number(val2))) {
            val1 = Number(val1);
            val2 = Number(val2);
        }
        if (sortType === "asc") {
            return val1 - val2;
        } else if (sortType === "desc") {
            return val2 - val1;
        }
    })
}

/**
 * bytes转换为size
 * @param: bytes 字节数
 **/
function bytesToSize(bytes) {
    let size = ''
    if (bytes < 0.1 * 1024) { // 小于0.1KB 则转化成B
        size = bytes + ' B'
    }
    else if (bytes < 0.1 * 1024 * 1024) { // 小于0.1MB 则转换成KB
        size = (bytes / 1024).toFixed(2) + ' KB'
    }
    else if (bytes < 0.1 * 1024 * 1024 * 1024) { // 小于0.1GB 则转换成MB
        size = (bytes / (1024 * 1024)).toFixed(2) + ' MB'
    }
    else if (bytes < 0.1 * 1024 * 1024 * 1024 * 1024) { // 小于0.1TB 则转换成GB
        size = (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
    }
    else if (bytes < 0.1 * 1024 * 1024 * 1024 * 1024 * 1024) { // 小于0.1PB 则转换成TB
        size = (bytes / (1024 * 1024 * 1024 * 1024)).toFixed(2) + ' TB'
    }
    else if (bytes < 0.1 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024) { // 小于0.1EB 则转换成PB
        size = (bytes / (1024 * 1024 * 1024 * 1024 * 1024)).toFixed(2) + ' PB'
    }
    return size
}

/**
 * 暂停
 * @param: ms 暂停毫秒数
 **/
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// 计算滚动条相对于页面底部的距离比例
function getScrollRate(){
    const winH = window.innerHeight; //页面可视区域高度
    const pageH = $("#page_content").height(); //页面总高度
    const scrollT = document.body.scrollTop || window.pageYOffset; //滚动条top
    return (pageH - winH - scrollT) / winH;
}

// 判断元素出现滚动条
function hasScrollbar() {
    // 判断是否大于2是因为我观察到部分情况下body可滚动的高度会比可视区域大1
    return (document.body.scrollHeight - (window.innerHeight || document.documentElement.clientHeight)) > 2;
}
