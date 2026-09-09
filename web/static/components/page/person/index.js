import "../../card/media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

export class PagePerson extends CustomElement {
  static properties = {
    page_title: { attribute: "page-title" },
    page_subtitle: { attribute: "page-subtitle" },
    media_type: { attribute: "media-type" },
    tmdbid: { attribute: "media-tmdbid" },
    person_list: { type: Array },
    _loading: { state: true },
    _error: { state: true },
  };

  constructor() {
    super();
    this.person_list = [];
    this._loading = true;
    this._error = "";
  }

  firstUpdated() {
    this._loadPeople();
  }

  _loadPeople(retry = false) {
    this._loading = true;
    this._error = "";
    const params = { tmdbid: this.tmdbid, type: this.media_type };
    const receive = (ret) => {
      if (!this.isConnected) return;
      this._loading = false;
      if (ret?.code === 0 && Array.isArray(ret.data)) this.person_list = ret.data;
      else this._error = ret?.msg || "暂时无法获取演职人员，请稍后重试。";
    };
    if (retry) {
      ajax_post("media_person", params, (ret) => {
        if (!this.isConnected) return;
        if (ret?.code === 0) Golbal.save_page_data("media_person" + this.media_type, ret);
        receive(ret);
      });
    } else Golbal.get_cache_or_ajax("media_person", this.media_type, params, receive);
  }

  render() {
    const detailPath = Golbal.build_nav_path("media_detail", { type: this.media_type, id: this.tmdbid });
    return html`
      <div class="container-xl">
        <header class="nt-discovery-header">
          <div class="nt-discovery-eyebrow">探索 · CAST & CREW</div>
          <div class="d-flex align-items-start justify-content-between gap-3 flex-wrap">
            <div>
              <h1 class="nt-discovery-title">${this.page_title || "演职人员"}${!this._loading && !this._error ? html` <span class="text-muted fs-3">${this.person_list.length}</span>` : nothing}</h1>
              <p class="nt-discovery-description">${this.page_subtitle} · 了解演员阵容，发现更多参演作品。</p>
            </div>
            <button type="button" class="btn btn-outline-primary" @click=${() => navmenu(detailPath)}>返回作品详情 →</button>
          </div>
        </header>
        <div class="d-grid gap-3 grid-media-card" aria-busy=${this._loading ? "true" : "false"}>
          ${this._error ? html`
            <div class="nt-media-state" role="status"><h2>演员信息暂时无法加载</h2><p>${this._error}</p>
              <button type="button" class="btn btn-primary" @click=${() => this._loadPeople(true)}>重新加载</button></div>`
          : this._loading ? Array.from({ length: 12 }, () => html`<person-card lazy="1" aria-hidden="true"></person-card>`)
          : this.person_list.length ? this.person_list.map((item) => html`
            <person-card person-id=${item.id} person-image=${item.image} person-name=${item.name} person-role=${item.role}
              @click=${() => navmenu(Golbal.build_nav_path("recommend", {
                type: this.media_type, subtype: "person", personid: item.id, title: "参演作品", subtitle: item.name,
              }))}></person-card>`)
          : html`<div class="nt-media-state" role="status"><h2>暂无演职人员信息</h2><p>该作品暂未提供演员资料，可以返回查看其他作品信息。</p></div>`}
        </div>
      </div>`;
  }
}

window.customElements.define("page-person", PagePerson);
