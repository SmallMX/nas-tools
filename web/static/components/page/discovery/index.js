import "../../card/media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";
import "./navigation.js";

export class PageDiscovery extends CustomElement {
  static properties = {
    discovery_type: { attribute: "discovery-type" },
    _slide_card_list: { state: true },
    _slide_errors: { state: true },
    _media_type_list: { state: true },
    ranking_category: { attribute: "ranking-category" },
  };

  constructor() {
    super();
    this._slide_card_list = {};
    this._slide_errors = {};
    this.ranking_category = "all";
    this._queue = [];
    this._queuedKeys = new Set();
    this._activeKeys = new Set();
    this._media_type_list = {
      "RANKING": [
        { type: "TRENDING", subtype: "tmdb", title: "TMDB 流行趋势", category: "all", ranking: true },
        { type: "MOV", subtype: "dbom", title: "豆瓣正在热映", category: "movie" },
        { type: "TV", subtype: "bangumi", title: "Bangumi 每日放送", category: "anime" },
        { type: "MOV", subtype: "hm", title: "TMDB 热门电影", category: "movie" },
        { type: "TV", subtype: "ht", title: "TMDB 热门剧集", category: "tv" },
        { type: "MOV", subtype: "dbhm", title: "豆瓣热门电影", category: "movie" },
        { type: "TV", subtype: "dbht", title: "豆瓣热门剧集", category: "tv" },
        { type: "TV", subtype: "dbdh", title: "豆瓣热门动漫", category: "anime" },
        { type: "MOV", subtype: "dbnewmovie", title: "豆瓣最新电影", category: "movie" },
        { type: "TV", subtype: "dbnewtv", title: "豆瓣最新剧集", category: "tv" },
        { type: "MOV", subtype: "dbtop", title: "豆瓣电影 TOP250", category: "movie", ranking: true },
        { type: "TV", subtype: "dbct", title: "豆瓣华语口碑剧集榜", category: "tv", ranking: true },
        { type: "TV", subtype: "dbgt", title: "豆瓣全球口碑剧集榜", category: "tv", ranking: true },
      ],
      "BANGUMI": [
        {
          type: "TV",
          title:"星期一",
          subtype :"bangumi",
          week :"1",
        },
        {
          type: "TV",
          title:"星期二",
          subtype :"bangumi",
          week :"2",
        },
        {
          type: "TV",
          title:"星期三",
          subtype :"bangumi",
          week :"3",
        },
        {
          type: "TV",
          title:"星期四",
          subtype :"bangumi",
          week :"4",
        },
        {
          type: "TV",
          title:"星期五",
          subtype :"bangumi",
          week :"5",
        },
        {
          type: "TV",
          title:"星期六",
          subtype :"bangumi",
          week :"6",
        },
        {
          type: "TV",
          title:"星期日",
          subtype :"bangumi",
          week :"7",
        },
      ]
    }
  }

  firstUpdated() {
    this._observeSections();
  }

  updated(changedProperties) {
    if (changedProperties.has("ranking_category")) this._observeSections();
  }

  disconnectedCallback() {
    this._observer?.disconnect();
    this._queue = [];
    this._queuedKeys.clear();
    super.disconnectedCallback();
  }

  _sectionKey(item) {
    return `${item.type}:${item.subtype}:${item.week || ""}`;
  }

  _sections() {
    const items = this._media_type_list[this.discovery_type] || [];
    if (this.discovery_type !== "RANKING" || this.ranking_category === "all") return items;
    return items.filter(item => this.ranking_category === "rank" ? item.ranking : item.category === this.ranking_category);
  }

  _selectCategory(category) {
    this.ranking_category = category;
    this.setAttribute("ranking-category", category);
    this.updateComplete.then(() => {
      if (this.isConnected) window_history();
    });
  }

  _observeSections() {
    if (!this.isConnected) return;
    this._observer?.disconnect();
    const sections = new Map(this._sections().map(item => [this._sectionKey(item), item]));
    const load = element => {
      const key = element.dataset.discoveryKey;
      if (sections.has(key)) this._queueSection(sections.get(key));
    };
    if (typeof IntersectionObserver === "function") {
      this._observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            this._observer.unobserve(entry.target);
            load(entry.target);
          }
        }
      }, { rootMargin: "300px" });
    }
    for (const element of this.querySelectorAll("custom-slide[data-discovery-key]")) {
      const key = element.dataset.discoveryKey;
      if (this._slide_card_list[key] !== undefined || this._slide_errors[key]) continue;
      if (this._observer) this._observer.observe(element);
      else load(element);
    }
    this._drainQueue();
  }

  _queueSection(item, retry = false) {
    const key = this._sectionKey(item);
    if (this._activeKeys.has(key) || this._queuedKeys.has(key)) return;
    if (!retry && (this._slide_card_list[key] !== undefined || this._slide_errors[key])) return;
    this._queue.push({ item, retry });
    this._queuedKeys.add(key);
    this._drainQueue();
  }

  _drainQueue() {
    const visibleKeys = new Set(this._sections().map(item => this._sectionKey(item)));
    while (this.isConnected && this._activeKeys.size < 3 && this._queue.length) {
      const task = this._queue.shift();
      const key = this._sectionKey(task.item);
      this._queuedKeys.delete(key);
      if (!visibleKeys.has(key)) continue;
      this._activeKeys.add(key);
      this._loadSection(task.item, task.retry).finally(() => {
        this._activeKeys.delete(key);
        this._drainQueue();
      });
    }
  }

  _loadSection(item, retry = false) {
    const key = this._sectionKey(item);
    const cacheName = `discovery:v2:${this.discovery_type}:${key}`;
    const cached = Golbal.get_page_data(cacheName);
    if (!retry && cached?.savedAt > Date.now() - 5 * 60 * 1000 && Array.isArray(cached.Items) && cached.Items.length) {
      this._slide_card_list = { ...this._slide_card_list, [key]: cached.Items };
      return Promise.resolve();
    }
    this._slide_errors = { ...this._slide_errors, [key]: "" };
    this._slide_card_list = { ...this._slide_card_list, [key]: undefined };
    const params = { type: item.type, subtype: item.subtype, page: 1, week: item.week };
    return NasToolsUI.pageAction("get_recommend", params, ret => {
      if (!this.isConnected) return;
      if (ret?.code !== 0 || !Array.isArray(ret.Items)) {
        this._slide_errors = { ...this._slide_errors, [key]: ret?.msg || "暂时无法获取内容，请稍后重试。" };
        return;
      }
      this._slide_card_list = { ...this._slide_card_list, [key]: ret.Items };
      // Failed and empty responses must remain retryable on the next page visit.
      if (ret.Items.length) Golbal.save_page_data(cacheName, { Items: ret.Items, savedAt: Date.now() });
    }, true, false);
  }

  _scrollToWeek(week) {
    const section = this.querySelector(`[data-discovery-week="${week}"]`);
    section?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" });
    section?.querySelector(".nt-slide__viewport")?.focus({ preventScroll: true });
  }

  render() {
    const bangumi = this.discovery_type === "BANGUMI";
    const today = String(new Date().getDay() || 7);
    return html`
      <div class="container-xl nt-discovery-page nt-explore-page ${bangumi ? "" : "nt-ranking-page"}">
        ${bangumi ? html`
          <h1 class="visually-hidden">Bangumi 每日放送</h1>
          <discovery-navigation active-source="bangumi"></discovery-navigation>` : html`
          <h1 class="visually-hidden">榜单推荐</h1>
          <nav class="nt-explore-sources" aria-label="榜单分类">
            ${[{ key: "all", title: "全部" }, { key: "movie", title: "电影" }, { key: "tv", title: "电视剧" }, { key: "anime", title: "动漫" }, { key: "rank", title: "榜单" }].map(category => html`
              <button type="button" class="nt-ranking-category nt-explore-source" data-ranking-category=${category.key}
                aria-pressed=${this.ranking_category === category.key ? "true" : "false"}
                @click=${() => this._selectCategory(category.key)}>${category.title}</button>`)}
          </nav>`}
        ${bangumi ? html`
          <nav class="nt-explore-filters" aria-label="按星期浏览每日放送">
            <div class="nt-explore-filter-row">
              <span class="nt-explore-filter-label">放送</span>
              <div class="nt-explore-filter-options">
                ${this._media_type_list.BANGUMI.map((item) => html`
                  <button type="button" class="nt-explore-chip" aria-current=${item.week === today ? "date" : nothing}
                    @click=${() => this._scrollToWeek(item.week)}>${item.title}${item.week === today ? " · 今天" : ""}</button>`)}
              </div>
            </div>
          </nav>` : nothing}
        ${this._sections().map((item) => html`
          <custom-slide data-discovery-key=${this._sectionKey(item)} data-discovery-week=${item.week || ""}
            slide-title=${item.title}
            slide-status=${this._slide_errors[this._sectionKey(item)] ? "error" : this._slide_card_list[this._sectionKey(item)] ? "ready" : "loading"}
            slide-error=${this._slide_errors[this._sectionKey(item)] || ""}
            slide-empty-retry="1"
            @retry=${() => this._queueSection(item, true)}
            .slide_click=${Golbal.build_nav_path("recommend", { type: item.type, subtype: item.subtype, week: item.week ?? "", title: item.title })}
            lazy="normal-card"
            .slide_card=${this._slide_card_list[this._sectionKey(item)]
              ? this._slide_card_list[this._sectionKey(item)].map((card) => html`
                <normal-card lazy="1" card-tmdbid=${card.id} card-mediatype=${card.type} card-showsub="1"
                  card-image=${card.image} card-vote=${card.vote} card-year=${card.year}
                  card-title=${card.title} card-overview=${card.overview} card-restype=${card.media_type}
                  card-weekday=${card.weekday} card-date=${card.date} card-site=${card.site}></normal-card>`)
              : Array.from({ length: 8 }, () => html`<normal-card-placeholder></normal-card-placeholder>`) }
          ></custom-slide>`)}
      </div>`;
  }
}

window.customElements.define("page-discovery", PageDiscovery);
