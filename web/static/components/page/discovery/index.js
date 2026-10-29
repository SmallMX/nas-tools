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
  };

  constructor() {
    super();
    this._slide_card_list = {};
    this._slide_errors = {};
    this._media_type_list = {
      "RANKING": [
        {
          type: "MOV",
          title:"正在热映",
          subtype :"dbom",
        },
        {
          type: "MOV",
          title:"即将上映",
          subtype :"dbnm",
        },
        {
          type: "TRENDING",
          title:"TMDB流行趋势",
          subtype :"tmdb",
        },
        {
          type: "MOV",
          title:"豆瓣最新电影",
          subtype :"dbnm",
        },
        {
          type: "MOV",
          title:"豆瓣热门电影",
          subtype :"dbhm",
        },
        {
          type: "MOV",
          title:"豆瓣电影TOP250",
          subtype :"dbtop",
        },
        {
          type: "TV",
          title:"豆瓣热门电视剧",
          subtype :"dbht",
        },
        {
          type: "TV",
          title:"华语口碑剧集榜",
          subtype :"dbct",
        },
        {
          type: "TV",
          title:"全球口碑剧集榜",
          subtype :"dbgt",
        }
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
    for (const item of this._media_type_list[this.discovery_type] ?? []) this._loadSection(item);
  }

  _loadSection(item, retry = false) {
    this._slide_errors = { ...this._slide_errors, [item.title]: "" };
    this._slide_card_list = { ...this._slide_card_list, [item.title]: undefined };
    const params = { type: item.type, subtype: item.subtype, page: 1, week: item.week };
    const cacheName = this.discovery_type + item.title;
    const receive = (ret) => {
      if (!this.isConnected) return;
      if (ret?.code !== 0 || !Array.isArray(ret.Items)) {
        this._slide_errors = { ...this._slide_errors, [item.title]: ret?.msg || "暂时无法获取内容，请稍后重试。" };
        return;
      }
      this._slide_card_list = { ...this._slide_card_list, [item.title]: ret.Items };
    };
    if (retry) {
      ajax_post("get_recommend", params, (ret) => {
        if (!this.isConnected) return;
        if (ret?.code === 0) Golbal.save_page_data("get_recommend" + cacheName, ret);
        receive(ret);
      });
    } else {
      Golbal.get_cache_or_ajax("get_recommend", cacheName, params, receive);
    }
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
      <div class="container-xl nt-discovery-page ${bangumi ? "nt-explore-page" : ""}">
        ${bangumi ? html`
          <h1 class="visually-hidden">Bangumi 每日放送</h1>
          <discovery-navigation active-source="bangumi"></discovery-navigation>` : html`
        <header class="nt-discovery-header">
          <div class="nt-discovery-eyebrow">探索 · DISCOVER</div>
          <h1 class="nt-discovery-title">发现下一部好作品</h1>
          <p class="nt-discovery-description">从热门榜单到每周新番，找到值得收藏的影视。</p>
        </header>
        <div class="nt-discovery-banner">
          <div>
            <h2>海量影视资源，发现更多精彩</h2>
            <p>汇聚 TMDB 与豆瓣榜单，按类型、评分和地区探索感兴趣的作品。</p>
          </div>
          <div class="nt-discovery-banner__actions">
            <button type="button" class="btn btn-primary" @click=${() => navmenu("tmdb_movie")}>浏览电影 →</button>
            <button type="button" class="btn btn-outline-primary" @click=${() => navmenu("tmdb_tv")}>浏览剧集 →</button>
          </div>
        </div>`}
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
        ${this._media_type_list[this.discovery_type]?.map((item) => html`
          <custom-slide data-discovery-week=${item.week || ""}
            slide-title=${item.title}
            slide-status=${this._slide_errors[item.title] ? "error" : this._slide_card_list[item.title] ? "ready" : "loading"}
            slide-error=${this._slide_errors[item.title] || ""}
            @retry=${() => this._loadSection(item, true)}
            .slide_click=${Golbal.build_nav_path("recommend", { type: item.type, subtype: item.subtype, week: item.week ?? "", title: item.title })}
            lazy="normal-card"
            .slide_card=${this._slide_card_list[item.title]
              ? this._slide_card_list[item.title].map((card) => html`
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
