import "../../card/media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

export class DiscoveryFilters extends CustomElement {
  static properties = {
    mode: {}, provider: {}, page: {},
    filter_config: { type: Object, attribute: "filter-config" },
    params: { type: Object },
    _fields: { state: true }, _loading: { state: true }, _error: { state: true },
  };

  constructor() {
    super();
    this.mode = "tmdb";
    this.provider = "";
    this.page = "tmdb_movie";
    this.filter_config = {};
    this.params = {};
    this._fields = null;
    this._loading = false;
    this._error = "";
    this._requestId = 0;
  }

  firstUpdated() {
    if (this.mode === "streaming") this._loadFilters();
  }

  disconnectedCallback() {
    this._requestId++;
    super.disconnectedCallback();
  }

  _baseFields() {
    return Object.entries(this.filter_config || {}).map(([key, field]) => ({
      key, name: key === "category" ? "种类" : field.name,
      options: field.options || [],
      default: key === "category" ? "tv" : key === "sort" ? "hot" : "",
    }));
  }

  _loadFilters() {
    const requestId = ++this._requestId;
    this._loading = true;
    this._error = "";
    NasToolsUI.pageAction("get_streaming_filters", {
      source: this.provider, category: this.params?.category || "tv",
    }, ret => {
      if (!this.isConnected || requestId !== this._requestId) return;
      this._loading = false;
      if (ret?.code !== 0 || !Array.isArray(ret.Filters)) {
        this._error = ret?.msg || "暂时无法加载完整筛选条件。";
        return;
      }
      this._fields = ret.Filters.filter(field => field && typeof field.key === "string" && Array.isArray(field.options));
    }, true, false);
  }

  _select(key, value) {
    if (this.mode === "streaming") {
      const params = key === "category"
        ? { category: value, sort: "hot" }
        : { ...this.params, [key]: value };
      navmenu(Golbal.build_nav_path(this.provider, { params: JSON.stringify(params) }));
    } else if (key === "media_type") {
      navmenu(value === "TV" ? "tmdb_tv" : "tmdb_movie");
    } else {
      navmenu(Golbal.build_nav_path(this.page, { params: JSON.stringify({ ...this.params, [key]: value }) }));
    }
  }

  _renderField(field) {
    const selected = String(this.params?.[field.key] ?? field.default ?? "");
    const label = field.key === "category" ? "种类" : field.name;
    return html`
      <div class="nt-explore-filter-row" data-filter-key=${field.key}>
        <span class="nt-explore-filter-label">${label}</span>
        <div class="nt-explore-filter-options" role="group" aria-label=${label}>
          ${field.options.map(option => html`
            <button type="button" class="nt-explore-chip" data-filter-value=${String(option.value)}
              aria-pressed=${String(option.value) === selected ? "true" : "false"}
              @click=${() => this._select(field.key, String(option.value))}>${this._renderCheck(String(option.value) === selected)}${option.name}</button>`)}
        </div>
      </div>`;
  }

  _renderCheck(selected) {
    return selected ? html`<svg class="nt-explore-chip__check" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 4 4L19 6"></path></svg>` : nothing;
  }

  render() {
    const fields = this._fields ?? this._baseFields();
    return html`
      <section class="nt-explore-filters" aria-label="筛选作品" aria-busy=${String(this._loading)}>
        ${this.mode === "tmdb" ? html`
          <div class="nt-explore-filter-row" data-filter-key="media_type">
            <span class="nt-explore-filter-label">种类</span>
            <div class="nt-explore-filter-options" role="group" aria-label="种类">
              ${[{ value: "MOV", name: "电影" }, { value: "TV", name: "电视剧" }].map(option => html`
                <button type="button" class="nt-explore-chip" data-filter-value=${option.value}
                  aria-pressed=${(this.page === "tmdb_tv" ? "TV" : "MOV") === option.value ? "true" : "false"}
                  @click=${() => this._select("media_type", option.value)}>${this._renderCheck((this.page === "tmdb_tv" ? "TV" : "MOV") === option.value)}${option.name}</button>`)}
            </div>
          </div>` : nothing}
        ${fields.map(field => this._renderField(field))}
        ${this._loading ? html`<p class="nt-explore-filter-status" role="status">正在加载筛选条件…</p>` : nothing}
        ${this._error ? html`
          <div class="nt-explore-filter-status" role="status">
            <span>${this._error}</span>
            <button type="button" class="btn btn-outline-primary btn-sm" @click=${() => this._loadFilters()}>重新加载筛选</button>
          </div>` : nothing}
      </section>`;
  }
}

window.customElements.define("discovery-filters", DiscoveryFilters);
