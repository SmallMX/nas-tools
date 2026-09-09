import "../media-styles.js";
import { html } from "../../utility/lit-core.min.js";
import { CustomElement } from "../../utility/utility.js";

export class NormalCardPlaceholder extends CustomElement {
  static render_placeholder() {
    return html`<div class="nt-media-skeleton nt-media-skeleton--poster"></div>`;
  }

  render() {
    return html`
      <div class="nt-media-loading" aria-hidden="true">
        ${NormalCardPlaceholder.render_placeholder()}
        <div class="nt-media-skeleton nt-media-skeleton--line"></div>
        <div class="nt-media-skeleton nt-media-skeleton--line nt-media-skeleton--short"></div>
      </div>`;
  }
}

window.customElements.define("normal-card-placeholder", NormalCardPlaceholder);
