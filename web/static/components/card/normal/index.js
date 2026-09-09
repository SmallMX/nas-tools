import { NormalCardPlaceholder } from "./placeholder.js"; export { NormalCardPlaceholder };
import "../media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

export class NormalCard extends CustomElement {
  static properties = {
    tmdb_id: { attribute: "card-tmdbid" },
    res_type: { attribute: "card-restype" },
    media_type: { attribute: "card-mediatype" },
    show_sub: { attribute: "card-showsub" },
    title: { attribute: "card-title" },
    date: { attribute: "card-date" },
    vote: { attribute: "card-vote" },
    image: { attribute: "card-image" },
    overview: { attribute: "card-overview" },
    year: { attribute: "card-year" },
    site: { attribute: "card-site" },
    weekday: { attribute: "card-weekday" },
    lazy: {},
    _placeholder: { state: true },
    _imageFailed: { state: true },
  };

  constructor() {
    super();
    this.lazy = "0";
    this._placeholder = true;
    this._imageFailed = false;
  }

  willUpdate(changedProperties) {
    if (changedProperties.has("image")) {
      this._placeholder = true;
      this._imageFailed = false;
    }
  }

  render() {
    const detailPath = Golbal.build_nav_path("media_detail", { type: this.media_type, id: this.tmdb_id });
    const title = this.title || "未命名影视";
    const meta = [this.year, this.site || this.res_type].filter(Boolean).join(" · ");
    return html`
      <article class="nt-media-card">
        <a class="nt-media-card__link" href=${Golbal.build_nav_path("/", { next: detailPath })} aria-label=${`查看《${title}》详情`}
          @click=${(event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            navmenu(detailPath);
          }}>
          <div class="nt-media-card__poster">
            ${this._placeholder ? html`<div class="nt-media-skeleton nt-media-skeleton--poster" aria-hidden="true"></div>` : nothing}
            <img src=${this.lazy == "1" ? nothing : this._imageFailed ? Golbal.noImage : this.image || Golbal.noImage}
              alt="" decoding="async" loading="lazy"
              @load=${() => { this._placeholder = false; }}
              @error=${() => { this._imageFailed = true; this._placeholder = false; }}>
            ${this.weekday || this.res_type ? html`<span class="nt-media-card__badge">${this.weekday || this.res_type}</span>` : nothing}
            ${Number(this.vote) > 0 ? html`<span class="nt-media-card__badge nt-media-card__rating" aria-label=${`评分 ${this.vote}`}>${this.vote}</span>` : nothing}
            ${this.overview ? html`<div class="nt-media-card__summary"><p>${this.overview}</p></div>` : nothing}
          </div>
          <h3 class="nt-media-card__title" title=${title}>${title}</h3>
          <div class="nt-media-card__meta">${meta || this.date || "年份待补充"}</div>
        </a>
        ${this.show_sub == "1" ? html`
          <div class="nt-media-card__footer">
            <button type="button" class="nt-media-card__search" aria-label=${`搜索《${title}》资源`}
              @click=${(event) => {
                event.stopPropagation();
                media_search(String(this.tmdb_id ?? ""), String(this.title ?? ""), String(this.media_type ?? ""));
              }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m16 16 4.5 4.5"></path></svg>搜索资源
            </button>
          </div>` : nothing}
      </article>`;
  }
}

window.customElements.define("normal-card", NormalCard);
