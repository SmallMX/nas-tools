import "../media-styles.js";
import { html } from "../../utility/lit-core.min.js";
import { CustomElement, Golbal } from "../../utility/utility.js";

export class PersonCard extends CustomElement {
  static properties = {
    person_id: { attribute: "person-id" },
    person_image: { attribute: "person-image" },
    person_name: { attribute: "person-name" },
    person_role: { attribute: "person-role" },
    lazy: {},
  };

  constructor() {
    super();
    this.lazy = "0";
  }

  render() {
    return html`
      <button type="button" class="nt-person-card" ?disabled=${!this.person_id}
        aria-label=${this.person_name ? `查看 ${this.person_name} 的参演作品` : "正在加载人物信息"}>
        <span class="nt-person-card__portrait">
          <custom-img lazy=${this.lazy} img-src=${this.person_image} img-noimage=${Golbal.noImage_person}
            img-ratio="100%" img-style="object-fit:cover;width:100%;height:100%;"></custom-img>
        </span>
        <span class="nt-person-card__name">${this.person_name || "正在加载…"}</span>
        <span class="nt-person-card__role">${this.person_role || (this.person_name ? "演职人员" : "")}</span>
      </button>`;
  }
}

window.customElements.define("person-card", PersonCard);
