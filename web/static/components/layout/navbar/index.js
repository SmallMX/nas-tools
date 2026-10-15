import { LayoutNavbarButton } from "./button.js"; export { LayoutNavbarButton };
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement } from "../../utility/utility.js";

// name: 导航分组或页面名称；访问权限由后端页面权限表决定
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
    layout_page_permissions: { attribute: "layout-page-permissions", type: Object },
    _active_name: { state: true},
  };

  constructor() {
    super();
    this.layout_gopage = "";
    this.layout_appversion = "v0.7.0";
    this.layout_userpris = [];
    this.layout_page_permissions = {};
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
    // 保留按用户权限顺序选择常用首页的行为，分组名不参与权限判断。
    const entryPages = navbar_list.map((entry) => entry.page ?? entry.list?.[0]?.page);
    const item = this.layout_userpris
      .map((permission) => entryPages.find((page) => {
        const required = this._page_permissions(page);
        return required.length === 1 && required[0] === permission;
      }) ?? entryPages.find((page) => this._page_permissions(page).includes(permission)))
      .find((page) => page);
    const page = item ?? navbar_list.flatMap((entry) => entry.list ?? [entry])
      .find((entry) => this._can_view_page(entry.page))?.page;
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
    const path = String(page ?? window.history.state?.page ?? "").replace(/^\//, "").split("?")[0];
    const aliases = { resources: "sitelist", userdownloader: "brushtask", download_setting: "downloader", tmdbcache: "media_setting" };
    const requestedPage = aliases[path] ?? path;
    const parent = navbar_list.find(
      (item) => item.page === requestedPage || item.relatedPages?.includes(requestedPage)
    );
    this._active_name = parent?.page ?? requestedPage;
    this.show_collapse(this._active_name);
  }

  _page_permissions(page) {
    const permission = this.layout_page_permissions?.[`/${page}`];
    return Array.isArray(permission) ? permission : permission ? [permission] : [];
  }

  _can_view_page(page) {
    const permissions = this._page_permissions(page);
    return permissions.includes("*") || permissions.some(
      (permission) => this.layout_userpris.includes(permission)
    );
  }

  _can_view_item(item) {
    return item.list?.length
      ? item.list.some((child) => this._can_view_page(child.page))
      : this._can_view_page(item.page);
  }

  show_collapse(page) {
    for (const item of this.querySelectorAll("[id^='lit-navbar-collapse-']")) {
      for (const a of item.querySelectorAll("a")) {
        if (page === a.getAttribute("data-lit-page")) {
          item.classList.add("show");
          const trigger = this.querySelector(`button[data-bs-target='#${item.id}']`);
          trigger?.classList.remove("collapsed");
          trigger?.setAttribute("aria-expanded", "true");
          return;
        }
      }
    }
  }

  render() {
    return html`
      <style>
        .lit-navbar-fixed { background: var(--nt-sidebar); position: fixed; inset: 0 auto 0 0; z-index: 1031; overflow: hidden; }
        .lit-navbar-fixed .lit-navbar-canvas { width: var(--app-sidebar-width) !important; height: 100dvh !important; max-height: 100dvh; min-height: 0; overflow: hidden; background: var(--nt-sidebar) !important; color: var(--nt-sidebar-text); }
        .lit-navbar-scroll { flex: 1 1 auto; min-height: 0; max-height: 100%; overflow-x: hidden; overflow-y: auto !important; overscroll-behavior-y: contain; scrollbar-width: thin; scrollbar-color: #3d5e4e transparent; }
        .lit-sidebar-brand { min-height: var(--app-header-height); border-bottom: 1px solid #2b4437; }
        .lit-navbar-canvas .accordion-button { background: transparent; color: #9cb6a8; box-shadow: none; border: 0; font-size: 11px; letter-spacing: 1px; font-weight: 550; }
        .lit-navbar-canvas .accordion-button::after { filter: brightness(0) invert(1); opacity: .45; width: 12px; height: 12px; background-size: 12px; }
        .lit-navbar-canvas .nav-link { color: var(--nt-sidebar-text); font-size: 13px; min-height: 38px; border-radius: 7px; }
        .lit-navbar-canvas .nav-link-icon { color: inherit; opacity: .9; margin-right: 10px; }
        .lit-navbar-canvas .nav-link-icon .icon { width: 19px; height: 19px; stroke-width: 1.6; }
        .lit-navbar-canvas .nav-link:hover { background: #254438; color: #fff; }
        .lit-navbar-canvas .lit-navbar-accordion-item-active { background: #e7f2eb; color: #185b47; font-weight: 600; }
        .lit-navbar-canvas .lit-navbar-accordion-item-active:hover { background: #d9eadd; color: #185b47; }
        .nt-sidebar-footer { color: #9cb6a8; font-size: 11px; padding: 16px; border-top: 1px solid #2b4437; text-align: center; }
        .nt-sidebar-footer:hover { color: #d3e0d7; }
        .lit-navbar-canvas .btn-close { filter: invert(1); }
        @media (min-width: 992px) {
          .lit-navbar-canvas { position: static !important; visibility: visible !important; transform: none !important; }
          .lit-navbar-fixed, .lit-navbar-fixed > .container-fluid { width: var(--app-sidebar-width) !important; height: 100dvh; max-height: 100dvh; min-height: 0; padding: 0; overflow: hidden; }
        }
        @media (max-width: 991.98px) { layout-navbar.lit-navbar { width: 0; min-height: 0 !important; padding: 0 !important; border: 0 !important; } }
      </style>
      <div class="container-fluid">
        <aside class="offcanvas offcanvas-start d-flex lit-navbar-canvas" tabindex="-1" id="litLayoutNavbar" aria-label="主导航">
          <div class="d-flex flex-row flex-grow-1 lit-navbar-scroll">
            <div class="d-flex flex-column flex-grow-1">
              <div class="lit-sidebar-brand d-flex align-items-center gap-2 px-3">
                <span class="nt-brand-mark" aria-hidden="true">NT</span>
                <div class="flex-grow-1">
                  <div class="nt-brand-name">NAS-Tools</div>
                  <div class="nt-brand-caption">你的媒体管理工作台</div>
                </div>
                <button type="button" class="btn-close d-lg-none" data-bs-dismiss="offcanvas" aria-label="关闭导航"></button>
              </div>
              <div class="accordion px-2 py-3 flex-grow-1">
                ${navbar_list.map((item, index) => ( html`
                  ${this._can_view_item(item)
                  ? html`
                    ${item.list?.length > 0
                    ? html`
                      <button class="accordion-button lit-navbar-accordion-button collapsed ps-2 pe-1 py-2" data-bs-toggle="collapse" data-bs-target="#lit-navbar-collapse-${index}" aria-expanded="false">
                        ${item.also??item.name}
                      </button>
                      <div class="accordion-collapse collapse" id="lit-navbar-collapse-${index}">
                        ${item.list.filter((drop) => this._can_view_page(drop.page))
                          .map((drop) => this._render_page_item(drop, true))}
                      </div>`
                    : this._render_page_item(item, false)
                    } `
                  : nothing }
                `))}
              </div>
              <div class="d-flex align-items-end">
                <a class="d-flex flex-grow-1 justify-content-center nt-sidebar-footer"
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
      href=${`/?next=${encodeURIComponent(item.page)}`} data-bs-dismiss="offcanvas"
      aria-current=${this._active_name === item.page ? "page" : nothing}
      data-lit-page=${item.page}
      @click=${ (event) => { event.preventDefault(); navmenu(item.page) }}>
      <span class="nav-link-icon">
        ${item.icon ?? nothing}
      </span>
      <span class="nav-link-title">
        ${item.also ?? item.name}
      </span>
    </a>`    
  }

}


window.customElements.define("layout-navbar", LayoutNavbar);
