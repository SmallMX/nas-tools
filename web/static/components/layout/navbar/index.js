import { LayoutNavbarButton } from "./button.js"; export { LayoutNavbarButton };
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement } from "../../utility/utility.js";

// name: 服务原名
// page: 导航路径
// icon: 项目图标
// : 显示别名 (可选)
const navbar_list = [
  {
    name: "探索",
    list: [
      {
        name: "榜单推荐",
        page: "ranking",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/align-box-bottom-center.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-align-box-bottom-center" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"></path>
            <path d="M9 15v2"></path>
            <path d="M12 11v6"></path>
            <path d="M15 13v4"></path>
          </svg>
        `,
      },
      {
        name: "TMDB电影",
        page: "tmdb_movie",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/movie.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-movie" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"></path>
            <path d="M8 4l0 16"></path>
            <path d="M16 4l0 16"></path>
            <path d="M4 8l4 0"></path>
            <path d="M4 16l4 0"></path>
            <path d="M4 12l16 0"></path>
            <path d="M16 8l4 0"></path>
            <path d="M16 16l4 0"></path>
          </svg>
        `,
      },
      {
        name: "TMDB电视剧",
        page: "tmdb_tv",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/device-tv.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-device-tv" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M3 7m0 2a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z"></path>
            <path d="M16 3l-4 4l-4 -4"></path>
          </svg>
        `,
      },
      {
        name: "BANGUMI",
        page: "bangumi",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/device-tv-old.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-device-tv-old" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
             <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
             <path d="M3 7m0 2a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v9a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2z"></path>
             <path d="M16 3l-4 4l-4 -4"></path>
             <path d="M15 7v13"></path>
             <path d="M18 15v.01"></path>
             <path d="M18 12v.01"></path>
          </svg>
        `,
      },
    ],
  },
  {
    name: "资源搜索",
    page: "search",
    icon: html`
      <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-search" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><circle cx="10" cy="10" r="7"></circle><line x1="21" y1="21" x2="15" y2="15"></line></svg>
    `,
  },
  {
    name: "站点管理",
    list: [
      {
        name: "站点维护",
        page: "site",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-server-2" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><rect x="3" y="4" width="18" height="8" rx="3"></rect><rect x="3" y="12" width="18" height="8" rx="3"></rect><line x1="7" y1="8" x2="7" y2="8.01"></line><line x1="7" y1="16" x2="7" y2="16.01"></line><path d="M11 8h6"></path><path d="M11 16h6"></path></svg>
        `,
      },
      {
        name: "数据统计",
        page: "statistics",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/chart-pie.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-chart-pie" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
             <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
             <path d="M10 3.2a9 9 0 1 0 10.8 10.8a1 1 0 0 0 -1 -1h-6.8a2 2 0 0 1 -2 -2v-7a.9 .9 0 0 0 -1 -.8"></path>
             <path d="M15 3.5a9 9 0 0 1 5.5 5.5h-4.5a1 1 0 0 1 -1 -1v-4.5"></path>
          </svg>
        `,
      },
      {
        name: "刷流任务",
        page: "brushtask",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/checklist.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-checklist" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M9.615 20h-2.615a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2h8a2 2 0 0 1 2 2v8"></path>
            <path d="M14 19l2 2l4 -4"></path>
            <path d="M9 8h4"></path>
            <path d="M9 12h2"></path>
          </svg>
        `,
      },
      {
        name: "站点资源",
        page: "sitelist",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/cloud-computing.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-cloud-computing" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M6.657 16c-2.572 0 -4.657 -2.007 -4.657 -4.483c0 -2.475 2.085 -4.482 4.657 -4.482c.393 -1.762 1.794 -3.2 3.675 -3.773c1.88 -.572 3.956 -.193 5.444 1c1.488 1.19 2.162 3.007 1.77 4.769h.99c1.913 0 3.464 1.56 3.464 3.486c0 1.927 -1.551 3.487 -3.465 3.487h-11.878"></path>
            <path d="M12 16v5"></path>
            <path d="M16 16v4a1 1 0 0 0 1 1h4"></path>
            <path d="M8 16v4a1 1 0 0 1 -1 1h-4"></path>
          </svg>
        `,
      },
    ],
  },
  {
    name: "下载管理",
    list: [
      {
        name: "正在下载",
        page: "downloading",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/loader.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-loader" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M12 6l0 -3"></path>
            <path d="M16.25 7.75l2.15 -2.15"></path>
            <path d="M18 12l3 0"></path>
            <path d="M16.25 16.25l2.15 2.15"></path>
            <path d="M12 18l0 3"></path>
            <path d="M7.75 16.25l-2.15 2.15"></path>
            <path d="M6 12l-3 0"></path>
            <path d="M7.75 7.75l-2.15 -2.15"></path>
          </svg>
        `,
      },
      {
        name: "近期下载",
        page: "downloaded",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-download" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"></path><polyline points="7 11 12 16 17 11"></polyline><line x1="12" y1="4" x2="12" y2="16"></line></svg>
        `,
      },
      {
        name: "自动删种",
        page: "torrent_remove",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/download-off.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-download-off" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 1.83 -1.19"></path>
            <path d="M7 11l5 5l2 -2m2 -2l1 -1"></path>
            <path d="M12 4v4m0 4v4"></path>
            <path d="M3 3l18 18"></path>
          </svg>
        `,
      },
    ],
  },
  {
    name: "工具",
    page: "tools",
    permission: "*",
    relatedPages: ["tools/site-signin"],
    icon: html`
      <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-tool" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
        <path d="M7 10h3v-3l-3.5 -3.5a6 6 0 0 1 8 8l6 6a2 2 0 0 1 -3 3l-6 -6a6 6 0 0 1 -8 -8z"></path>
      </svg>
    `,
  },
  {
    name: "服务",
    page: "service",
    icon: html`
      <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-layout-2" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><rect x="4" y="4" width="6" height="5" rx="2"></rect><rect x="4" y="13" width="6" height="7" rx="2"></rect><rect x="14" y="4" width="6" height="7" rx="2"></rect><rect x="14" y="15" width="6" height="5" rx="2"></rect></svg>
    `,
  },
  {
    name: "系统设置",
    also: "设置",
    list: [
      {
        name: "基础设置",
        page: "basic",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-settings" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round"><path stroke="none" d="M0 0h24v24H0z" fill="none"></path><path d="M10.325 4.317c.426 -1.756 2.924 -1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543 -.94 3.31 .826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756 .426 1.756 2.924 0 3.35a1.724 1.724 0 0 0 -1.066 2.573c.94 1.543 -.826 3.31 -2.37 2.37a1.724 1.724 0 0 0 -2.572 1.065c-.426 1.756 -2.924 1.756 -3.35 0a1.724 1.724 0 0 0 -2.573 -1.066c-1.543 .94 -3.31 -.826 -2.37 -2.37a1.724 1.724 0 0 0 -1.065 -2.572c-1.756 -.426 -1.756 -2.924 0 -3.35a1.724 1.724 0 0 0 1.066 -2.573c-.94 -1.543 .826 -3.31 2.37 -2.37c1 .608 2.296 .07 2.572 -1.065z"></path><circle cx="12" cy="12" r="3"></circle></svg>
        `,
      },
      {
        name: "媒体设置",
        page: "media_setting",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-movie" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M4 4m0 2a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2z"></path>
            <path d="M8 4l0 16"></path>
            <path d="M16 4l0 16"></path>
            <path d="M4 12l16 0"></path>
          </svg>
        `,
      },
      {
        name: "服务设置",
        page: "service_setting",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-automation" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M8 4a2 2 0 1 0 0 4a2 2 0 0 0 0 -4"></path>
            <path d="M16 16a2 2 0 1 0 0 4a2 2 0 0 0 0 -4"></path>
            <path d="M12 6h3a3 3 0 0 1 3 3v1"></path>
            <path d="M12 18h-3a3 3 0 0 1 -3 -3v-1"></path>
          </svg>
        `,
      },
      {
        name: "安全设置",
        page: "security_setting",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-shield-lock" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M12 3l8 4v5c0 5 -3.5 7.5 -8 9c-4.5 -1.5 -8 -4 -8 -9v-5z"></path>
            <path d="M10 13a2 2 0 1 1 4 0v2h-4z"></path>
          </svg>
        `,
      },
      {
        name: "实验室",
        page: "laboratory_setting",
        icon: html`
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-flask" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M9 3l6 0"></path>
            <path d="M10 9l4 0"></path>
            <path d="M10 3v6l-4 8a2 2 0 0 0 2 3h8a2 2 0 0 0 2 -3l-4 -8v-6"></path>
          </svg>
        `,
      },
      {
        name: "用户管理",
        page: "users",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/users.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-users" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M9 7m-4 0a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"></path>
            <path d="M3 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"></path>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
            <path d="M21 21v-2a4 4 0 0 0 -3 -3.85"></path>
          </svg>
        `,
      },
      {
        name: "消息通知",
        page: "notification",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/bell.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-bell" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M10 5a2 2 0 0 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3h-16a4 4 0 0 0 2 -3v-3a7 7 0 0 1 4 -6"></path>
            <path d="M9 17v1a3 3 0 0 0 6 0v-1"></path>
          </svg>
        `,
      },
      {
        name: "下载器",
        page: "downloader",
        icon: html`
          <!-- https://tabler-icons.io/static/tabler-icons/icons-png/download.png -->
          <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-download" width="24" height="24" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
            <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"></path>
            <path d="M7 11l5 5l5 -5"></path>
            <path d="M12 4l0 12"></path>
          </svg>
        `,
      },
    ],
  },
];

export class LayoutNavbar extends CustomElement {
  static properties = {
    layout_gopage: { attribute: "layout-gopage" },
    layout_appversion: { attribute: "layout-appversion"},
    layout_userpris: { attribute: "layout-userpris", type: Array },
    _active_name: { state: true},
  };

  constructor() {
    super();
    this.layout_gopage = "";
    this.layout_appversion = "v0.6.0";
    this.layout_userpris = navbar_list.map((item) => (item.name));
    this._active_name = "";
    this.classList.add("navbar", "navbar-vertical", "navbar-expand-lg", "lit-navbar-fixed", "lit-navbar");
  }

  firstUpdated() {
    // 加载页面
    if (this.layout_gopage) {
      navmenu(this.layout_gopage);
    } else if (window.history.state?.page) {
      //console.log("刷新页面");
      window_history_refresh();
    } else {
      this._open_default_page();
    }
    // 等首屏导航状态确定后再显示外壳，避免布局闪烁。
    setTimeout(() => {
      window.revealAppShell();
    }, 200);
  }

  _open_default_page() {
    const item = this.layout_userpris
      .map((permission) => navbar_list.find(
        (entry) => this._required_permissions(entry).includes(permission)
      ))
      .find((entry) => entry) ?? navbar_list.find((entry) => this._can_view_item(entry));
    const page = item?.page ?? item?.list?.[0]?.page;
    if (page) {
      navmenu(page);
      setTimeout(() => { this.show_collapse(page) }, 200);
      return;
    }

    document.querySelector("#page_content").innerHTML = `
      <div class="container-xl py-5">
        <div class="empty">
          <p class="empty-title">暂无可访问的功能</p>
          <p class="empty-subtitle text-muted">请联系管理员重新分配权限。</p>
        </div>
      </div>`;
  }

  update_active(page) {
    const requestedPage = page ?? window.history.state?.page;
    const parent = navbar_list.find(
      (item) => item.page === requestedPage || item.relatedPages?.includes(requestedPage)
    );
    this._active_name = parent?.page ?? requestedPage;
    this.show_collapse(this._active_name);
  }

  _required_permissions(item) {
    const permission = item.permission ?? item.name;
    return Array.isArray(permission) ? permission : [permission];
  }

  _can_view_item(item) {
    const permissions = this._required_permissions(item);
    return permissions.includes("*") || permissions.some(
      (permission) => this.layout_userpris.includes(permission)
    );
  }

  show_collapse(page) {
    for (const item of this.querySelectorAll("[id^='lit-navbar-collapse-']")) {
      for (const a of item.querySelectorAll("a")) {
        if (page === a.getAttribute("data-lit-page")) {
          item.classList.add("show");
          this.querySelectorAll(`button[data-bs-target='#${item.id}']`)[0].classList.remove("collapsed");
          return;
        }
      }
    }
  }

  render() {
    return html`
      <style>
        
        .lit-navbar-fixed {
          position: fixed;
          inset: 0 auto 0 0;
          z-index: 1031;
          overflow: hidden;
        }

        .lit-navbar-canvas {
          width: var(--app-sidebar-width) !important;
          height: 100vh;
          height: 100dvh;
          max-height: 100vh;
          max-height: 100dvh;
          min-height: 0;
          overflow: hidden;
          background: var(--tblr-bg-surface) !important;
        }

        .theme-light .lit-navbar-canvas {
          background: #ffffff !important;
        }

        .lit-navbar-scroll {
          flex: 1 1 auto;
          min-height: 0;
          max-height: 100%;
          overflow-x: hidden;
          overflow-y: auto !important;
          overscroll-behavior-y: contain;
          touch-action: pan-y;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: thin;
          scrollbar-color: var(--tblr-border-color) transparent;
        }

        .lit-navbar-scroll::-webkit-scrollbar {
          width: 0.375rem;
        }

        .lit-navbar-scroll::-webkit-scrollbar-thumb {
          border-radius: 999px;
          background: var(--tblr-border-color);
        }

        .lit-sidebar-brand {
          min-height: var(--app-header-height);
          border-bottom: 1px solid var(--tblr-border-color);
        }
        
        .lit-navbar-logo {
          width: 2.25rem;
          height: 2.25rem;
          object-fit: contain;
        }

        .theme-dark .lit-navbar-logo {
          filter: invert(1) grayscale(100%) brightness(200%);
        }

        @media (min-width: 993px) {
          .lit-navbar-canvas {
            position: static !important;
            visibility: visible !important;
            transform: none !important;
            height: 100vh;
            border-right: 1px solid var(--tblr-border-color);
          }

          .lit-navbar-fixed,
          .lit-navbar-fixed > .container-fluid {
            width: var(--app-sidebar-width);
            height: 100vh;
            height: 100dvh;
            max-height: 100vh;
            max-height: 100dvh;
            min-height: 0;
            padding: 0;
            overflow: hidden;
          }

          .lit-navbar-canvas {
            height: 100%;
            max-height: 100%;
          }
        }

        .theme-dark .lit-navbar-accordion-button {

        }
        .theme-light .lit-navbar-accordion-button {

        }
        .lit-navbar-accordion-button::after {
          
        }

        .lit-navbar-accordion-item, .lit-navbar-accordion-item-active {
          border-radius: 0.5rem;
          min-height: 2.5rem;
        }

        .theme-dark .lit-navbar-accordion-item:hover {
          background-color: #2a3551ca!important;
        }
        .theme-light .lit-navbar-accordion-item:hover {
          background-color: #f3f6f9 !important;
        }

        .theme-dark .lit-navbar-accordion-item-active {
          background-color: #414d6dca!important;
        }
        .theme-light .lit-navbar-accordion-item-active {
          background-color: rgba(var(--tblr-primary-rgb), 0.12) !important;
          color: var(--tblr-primary) !important;
        }

      </style>
      <div class="container-fluid">
        <aside class="offcanvas offcanvas-start d-flex lit-navbar-canvas" tabindex="-1" id="litLayoutNavbar" aria-label="主导航">
          <div class="d-flex flex-row flex-grow-1 lit-navbar-scroll">
            <div class="d-flex flex-column flex-grow-1">
              <div class="lit-sidebar-brand d-flex align-items-center gap-2 px-3">
                <img src="../static/img/logo-blue.png" alt="" class="lit-navbar-logo">
                <div class="flex-grow-1">
                  <div class="fw-bold">NAStool</div>
                  <div class="small text-muted">媒体管理控制台</div>
                </div>
                <button type="button" class="btn-close d-lg-none" data-bs-dismiss="offcanvas" aria-label="关闭导航"></button>
              </div>
              <div class="accordion px-2 py-3 flex-grow-1">
                ${navbar_list.map((item, index) => ( html`
                  ${this._can_view_item(item)
                  ? html`
                    ${item.list?.length > 0
                    ? html`
                      <button class="accordion-button lit-navbar-accordion-button collapsed ps-2 pe-1 py-2" style="font-size:1.1rem;" data-bs-toggle="collapse" data-bs-target="#lit-navbar-collapse-${index}" aria-expanded="false">
                        ${item.also??item.name}
                      </button>
                      <div class="accordion-collapse collapse" id="lit-navbar-collapse-${index}">
                        ${item.list.map((drop) => (this._render_page_item(drop, true)))}
                      </div>`
                    : this._render_page_item(item, false)
                    } `
                  : nothing }
                `))}
              </div>
              <div class="d-flex align-items-end">
                <a class="d-flex flex-grow-1 justify-content-center border rounded-3 m-3 p-2 text-muted"
                   href="https://github.com/SmallMX/nas-tools" target="_blank" rel="noopener noreferrer"
                   aria-label="查看源代码和 AGPL-3.0 许可证">
                  <span>
                    <strong>
                      <svg xmlns="http://www.w3.org/2000/svg" class="icon icon-tabler icon-tabler-brand-github" width="24" height="24"
                          viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" fill="none" stroke-linecap="round"
                          stroke-linejoin="round">
                        <path stroke="none" d="M0 0h24v24H0z" fill="none"></path>
                        <path d="M9 19c-4.3 1.4 -4.3 -2.5 -6 -3m12 5v-3.5c0 -1 .1 -1.4 -.5 -2c2.8 -.3 5.5 -1.4 5.5 -6a4.6 4.6 0 0 0 -1.3 -3.2a4.2 4.2 0 0 0 -.1 -3.2s-1.1 -.3 -3.5 1.3a12.3 12.3 0 0 0 -6.2 0c-2.4 -1.6 -3.5 -1.3 -3.5 -1.3a4.2 4.2 0 0 0 -.1 3.2a4.6 4.6 0 0 0 -1.3 3.2c0 4.6 2.7 5.7 5.5 6c-.6 .6 -.6 1.2 -.5 2v3.5"></path>
                      </svg>
                      ${this.layout_appversion} · 源代码 · AGPL-3.0
                    </strong>
                  </span>
                </a>
              </div>
            </div>
          </div>
        </aside>
      </div>
    `;
  }

  _render_page_item(item, child) {
    return html`
    <a class="nav-link lit-navbar-accordion-item${this._active_name === item.page ? "-active" : ""} my-1 p-2 ${child ? "ps-3" : "lit-navbar-accordion-button"}" 
      href="javascript:void(0)" data-bs-dismiss="offcanvas" aria-label="Close"
      style="${child ? "font-size:1rem" : "font-size:1.1rem;"}"
      data-lit-page=${item.page}
      @click=${ () => { navmenu(item.page) }}>
      <span class="nav-link-icon" ?hidden=${!child} style="color:var(--tblr-body-color);">
        ${item.icon ?? nothing}
      </span>
      <span class="nav-link-title">
        ${item.also ?? item.name}
      </span>
    </a>`    
  }

}


window.customElements.define("layout-navbar", LayoutNavbar);
