import "../../card/media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

export class PageMediainfo extends CustomElement {
  static properties = {
    media_type: { attribute: "media-type" },
    tmdbid: { attribute: "media-tmdbid" },
    media_info: { type: Object },
    similar_media: { type: Array },
    recommend_media: { type: Array },
    _loading: { state: true },
    _error: { state: true },
    _recommendState: { state: true },
    _recommendErrors: { state: true },
  };

  constructor() {
    super();
    this.media_info = {};
    this.similar_media = [];
    this.recommend_media = [];
    this._loading = true;
    this._error = "";
    this._recommendState = { sim: "loading", more: "loading" };
    this._recommendErrors = {};
  }

  firstUpdated() {
    this._loadDetail();
  }

  _loadDetail(retry = false) {
    this._loading = true;
    this._error = "";
    const params = { type: this.media_type, tmdbid: this.tmdbid };
    const receive = (ret) => {
      if (!this.isConnected) return;
      this._loading = false;
      if (ret?.code !== 0 || !ret.data) {
        this._error = ret?.msg || "未查询到 TMDB 媒体信息，请稍后重试。";
        return;
      }
      this.media_info = ret.data;
      this.tmdbid = ret.data.tmdbid;
      this._loadRecommendations("sim");
      this._loadRecommendations("more");
    };
    if (retry) {
      ajax_post("media_detail", params, (ret) => {
        if (!this.isConnected) return;
        if (ret?.code === 0) Golbal.save_page_data("media_detailinfo", ret);
        receive(ret);
      });
    } else Golbal.get_cache_or_ajax("media_detail", "info", params, receive);
  }

  _loadRecommendations(subtype, retry = false) {
    this._recommendState = { ...this._recommendState, [subtype]: "loading" };
    const params = { type: this.media_type, subtype, tmdbid: this.tmdbid, page: 1 };
    const receive = (ret) => {
      if (!this.isConnected) return;
      const failed = ret?.code !== 0 || !Array.isArray(ret.Items);
      this._recommendState = { ...this._recommendState, [subtype]: failed ? "error" : "ready" };
      this._recommendErrors = { ...this._recommendErrors, [subtype]: failed ? ret?.msg || "暂时无法获取推荐内容。" : "" };
      if (!failed) this[subtype === "sim" ? "similar_media" : "recommend_media"] = ret.Items;
    };
    if (retry) {
      ajax_post("get_recommend", params, (ret) => {
        if (!this.isConnected) return;
        if (ret?.code === 0) Golbal.save_page_data("get_recommend" + subtype, ret);
        receive(ret);
      });
    } else Golbal.get_cache_or_ajax("get_recommend", subtype, params, receive);
  }

  _renderRecommendations(items, subtype, title) {
    return html`
      <custom-slide slide-title=${title} lazy="normal-card"
        slide-status=${this._recommendState[subtype]} slide-error=${this._recommendErrors[subtype] || ""}
        @retry=${() => this._loadRecommendations(subtype, true)}
        .slide_click=${Golbal.build_nav_path("recommend", {
          type: this.media_type, subtype, tmdbid: this.tmdbid, title, subtitle: this.media_info.title,
        })}
        .slide_card=${this._recommendState[subtype] === "loading"
          ? Array.from({ length: 6 }, () => html`<normal-card-placeholder></normal-card-placeholder>`)
          : items.map((item) => html`
            <normal-card lazy="1" card-tmdbid=${item.id} card-mediatype=${item.type} card-showsub="1"
              card-image=${item.image} card-vote=${item.vote} card-year=${item.year}
              card-title=${item.title} card-overview=${item.overview}></normal-card>`) }>
      </custom-slide>`;
  }

  render() {
    const info = this.media_info;
    const tmdbLink = Golbal.safe_external_url(info.link);
    const doubanLink = Golbal.safe_external_url(info.douban_link);
    const actorsPath = Golbal.build_nav_path("discovery_person", {
      tmdbid: this.tmdbid, type: this.media_type, title: "演职人员", subtitle: info.title,
    });
    if (this._error) return html`
      <div class="container-xl nt-media-detail">
        <div class="nt-media-state" role="status"><h1 class="nt-discovery-title">作品详情暂时无法加载</h1><p>${this._error}</p>
          <button type="button" class="btn btn-primary" @click=${() => this._loadDetail(true)}>重新加载</button>
          <button type="button" class="btn btn-outline-primary ms-2" @click=${() => navmenu("ranking")}>浏览榜单</button>
        </div>
      </div>`;
    return html`
      <div class="container-xl nt-media-detail" aria-busy=${this._loading ? "true" : "false"}>
        <div class="nt-discovery-eyebrow">探索 · 作品详情</div>
        <section class="nt-media-detail__hero" aria-label="作品概览">
          ${info.background?.length ? html`
            <div class="nt-media-detail__backdrop" aria-hidden="true">
              <img src=${info.background[0]} alt="" style="width:100%;height:100%;object-fit:cover;" @error=${(event) => { event.target.hidden = true; }}>
            </div>` : nothing}
          <div class="nt-media-detail__hero-content">
            <div class="nt-media-detail__poster">
              ${this._loading ? html`<normal-card-placeholder></normal-card-placeholder>` : html`
                <custom-img img-src=${info.image} img-ratio="150%" img-style="width:100%;height:100%;object-fit:cover;"></custom-img>`}
            </div>
            <div class="nt-media-detail__heading">
              <h1>${this._loading ? "正在加载作品信息…" : info.title}${info.year ? html` <span class="nt-media-detail__year">(${info.year})</span>` : nothing}</h1>
              <div class="nt-media-detail__metadata">
                ${Number(info.vote) > 0 ? html`<span class="nt-media-detail__score">★ ${info.vote}</span>` : nothing}
                ${info.runtime ? html`<span>${info.runtime}</span>` : nothing}
                ${info.genres ? html`<span>${info.genres}</span>` : nothing}
              </div>
              <div class="nt-media-detail__links">
                ${info.tmdbid && tmdbLink ? html`<a href=${tmdbLink} target="_blank" rel="noopener noreferrer">TMDB · ${info.tmdbid} ↗</a>` : nothing}
                ${info.douban_id && doubanLink ? html`<a href=${doubanLink} target="_blank" rel="noopener noreferrer">豆瓣 · ${info.douban_id} ↗</a>` : nothing}
              </div>
              ${!this._loading ? html`
                <div class="btn-list">
                  <button type="button" class="btn btn-primary" @click=${() => media_search(String(this.tmdbid), info.title, this.media_type)}>
                    <svg class="icon" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" fill="none" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 4.5 4.5"></path></svg>搜索资源
                  </button>
                  ${info.actors?.length ? html`<button type="button" class="btn btn-outline-primary" @click=${() => navmenu(actorsPath)}>查看演职人员</button>` : nothing}
                </div>` : html`<div class="nt-media-skeleton nt-media-skeleton--line"></div>`}
            </div>
          </div>
        </section>
        <div class="nt-media-detail__columns">
          <section class="nt-media-detail__section">
            <h2>剧情简介</h2>
            <p class="nt-media-detail__overview">${this._loading ? "正在加载剧情简介…" : info.overview || "这部作品暂未提供剧情简介。"}</p>
            ${info.crews?.length ? html`
              <dl class="nt-media-detail__crew">${info.crews.map((item) => html`
                <div><dt>${Object.keys(item)[0]}</dt><dd>${Object.values(item)[0]}</dd></div>`)}</dl>` : nothing}
          </section>
          <section class="nt-media-detail__section">
            <h2>作品资料</h2>
            ${info.fact?.length ? html`
              <dl class="nt-media-detail__facts">${info.fact.map((item) => html`
                <div><dt>${Object.keys(item)[0]}</dt><dd>${Object.values(item)[0]}</dd></div>`)}</dl>`
              : html`<p class="nt-media-detail__overview">${this._loading ? "正在加载资料…" : "暂无更多作品资料。"}</p>`}
          </section>
        </div>
        ${info.actors?.length ? html`
          <custom-slide slide-title="演员阵容" .slide_click=${actorsPath} lazy="person-card"
            .slide_card=${info.actors.map((item) => html`
              <person-card lazy="1" person-id=${item.id} person-image=${item.image} person-name=${item.name} person-role=${item.role}
                @click=${() => navmenu(Golbal.build_nav_path("recommend", {
                  type: this.media_type, subtype: "person", personid: item.id, title: "参演作品", subtitle: item.name,
                }))}></person-card>`) }></custom-slide>` : nothing}
        ${!this._loading ? this._renderRecommendations(this.similar_media, "sim", "相似作品") : nothing}
        ${!this._loading ? this._renderRecommendations(this.recommend_media, "more", "你可能还喜欢") : nothing}
      </div>`;
  }
}

window.customElements.define("page-mediainfo", PageMediainfo);
