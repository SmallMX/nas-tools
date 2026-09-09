import "../../card/media-styles.js";
import { html, nothing } from "../../utility/lit-core.min.js";
import { CustomElement } from "../../utility/utility.js";

export class CustomSlide extends CustomElement {
  static properties = {
    slide_title: { attribute: "slide-title" },
    slide_click: { attribute: "slide-click" },
    slide_status: { attribute: "slide-status" },
    slide_error: { attribute: "slide-error" },
    lazy: { attribute: "lazy" },
    slide_card: { type: Array },
    _disabled: { state: true },
  };

  constructor() {
    super();
    this._disabled = 3;
    this.slide_title = "正在加载";
    this.slide_click = "";
    this.slide_status = "ready";
    this.slide_card = [];
  }

  render() {
    const cards = this.slide_card || [];
    return html`
      <section class="nt-slide" aria-label=${this.slide_title}>
        <header class="nt-slide__header">
          <h2 class="nt-slide__title">${this.slide_title}</h2>
          <div class="nt-slide__actions">
            ${this.slide_click ? html`<button type="button" class="nt-slide__more" @click=${this._openSlide}>查看全部 <span aria-hidden="true">→</span></button>` : nothing}
            <button type="button" class="nt-slide__arrow" ?hidden=${this._disabled === 3}
              ?disabled=${this._disabled === 0} aria-label=${`向前浏览${this.slide_title}`} @click=${() => this._slideNext(false)}>‹</button>
            <button type="button" class="nt-slide__arrow" ?hidden=${this._disabled === 3}
              ?disabled=${this._disabled === 2} aria-label=${`向后浏览${this.slide_title}`} @click=${() => this._slideNext(true)}>›</button>
          </div>
        </header>
        ${this.slide_status === "error" ? html`
          <div class="nt-media-state" role="status">
            <p>${this.slide_error || "暂时无法获取内容，请稍后重试。"}</p>
            <button class="btn btn-outline-primary btn-sm" type="button"
              @click=${() => this.dispatchEvent(new CustomEvent("retry", { bubbles: true }))}>重新加载</button>
          </div>` : this.slide_status !== "loading" && !cards.length ? html`
          <div class="nt-media-state" role="status"><p>暂无内容，稍后再来看看。</p></div>` : nothing}
        <div class="nt-slide__viewport media-slide-hide-scrollbar" tabindex="0" role="region"
          aria-label=${`${this.slide_title}，可左右滚动浏览`} aria-busy=${this.slide_status === "loading" ? "true" : "false"}
          ?hidden=${this.slide_status === "error" || (!cards.length && this.slide_status !== "loading")}
          @scroll=${this._countDisabled}>
          <div class="nt-slide__track media-slide-card-number">${cards}</div>
        </div>
      </section>`;
  }

  firstUpdated() {
    this._scrollbar = this.querySelector(".nt-slide__viewport");
    this._track = this.querySelector(".nt-slide__track");
    this._onResize = () => this._countMaxNumber();
    window.addEventListener("resize", this._onResize);
    this._resizeObserver = new ResizeObserver(this._onResize);
    this._resizeObserver.observe(this._scrollbar);
    this._countMaxNumber();
  }

  updated(changedProperties) {
    if (changedProperties.has("slide_card") || changedProperties.has("slide_status")) this._countMaxNumber();
  }

  disconnectedCallback() {
    window.removeEventListener("resize", this._onResize);
    this._resizeObserver?.disconnect();
    super.disconnectedCallback();
  }

  _openSlide() {
    if (this.slide_click) navmenu(this.slide_click);
  }

  _countMaxNumber() {
    if (!this._scrollbar || !this._track) return;
    const firstCard = this._track.firstElementChild;
    const width = firstCard?.getBoundingClientRect().width || 176;
    const gap = Number.parseFloat(getComputedStyle(this._track).columnGap) || 16;
    this._card_width = width + gap;
    this._card_max = Math.max(1, Math.floor((this._scrollbar.clientWidth + gap) / this._card_width));
    this._countDisabled();
  }

  _countDisabled() {
    if (!this._scrollbar || !this._card_width) return;
    const scrollLeft = this._scrollbar.scrollLeft;
    const maxLeft = this._scrollbar.scrollWidth - this._scrollbar.clientWidth;
    this._card_current = Math.max(0, Math.floor(scrollLeft / this._card_width));
    this._disabled = maxLeft <= 2 ? 3 : scrollLeft <= 2 ? 0 : scrollLeft >= maxLeft - 2 ? 2 : 1;
    if (this.lazy) {
      const cards = this._track.querySelectorAll(this.lazy);
      const showMax = Math.min(cards.length, this._card_current + this._card_max + 2);
      for (let i = this._card_current; i < showMax; i++) cards[i].removeAttribute("lazy");
    }
  }

  _slideNext(next) {
    if (!this._scrollbar) return;
    this._scrollbar.scrollBy({
      left: (next ? 1 : -1) * this._card_max * this._card_width,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  }
}

window.customElements.define("custom-slide", CustomSlide);
