import "../../card/media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

const sources = [
  { source: "tmdb", title: "TMDB", page: "tmdb_movie" },
  { source: "tencent", title: "腾讯视频", page: "tencent" },
  { source: "iqiyi", title: "爱奇艺", page: "iqiyi" },
  { source: "mgtv", title: "芒果视频", page: "mgtv" },
  { source: "bangumi", title: "Bangumi", page: "bangumi" },
];

export class DiscoveryNavigation extends CustomElement {
  static properties = { active_source: { attribute: "active-source" } };

  firstUpdated() {
    this.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  render() {
    return html`
      <nav class="nt-explore-sources" aria-label="探索数据源">
        ${sources.map(source => html`
          <a class="nt-explore-source" data-discovery-source=${source.source}
            href=${Golbal.build_nav_path("/", { next: source.page })}
            aria-current=${source.source === this.active_source ? "page" : nothing}
            @click=${event => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
              event.preventDefault();
              navmenu(source.page);
            }}>${source.title}</a>`)}
      </nav>`;
  }
}

window.customElements.define("discovery-navigation", DiscoveryNavigation);
