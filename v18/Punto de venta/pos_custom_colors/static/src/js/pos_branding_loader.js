/* @odoo-module */

import { Chrome } from "@point_of_sale/app/pos_app";
import { patch } from "@web/core/utils/patch";

patch(Chrome.prototype, {
  setup() {
    super.setup();
    this._loadCustomBranding();
  },

  async _loadCustomBranding() {
    const config = this.pos.config;

    if (!config.use_custom_branding) {
      console.log("Custom branding disabled");
      return;
    }

    console.log("Loading custom branding for config:", config.id);

    // Cargar CSS personalizado
    const cssUrl = `/pos/branding/css/${config.id}`;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = cssUrl;
    link.id = "pos-custom-branding-css";
    document.head.appendChild(link);

    // Si hay texto de branding sin logo
    if (config.branding_text && !config.custom_logo) {
      this._applyBrandingText(config.branding_text);
    }

    console.log("Custom branding loaded");
  },

  _applyBrandingText(text) {
    // Aplicar texto personalizado al logo
    const style = document.createElement("style");
    style.innerHTML = `
            .pos .pos-logo::after,
            .pos .pos-branding::after {
                content: "${text}" !important;
                font-size: 24px;
                font-weight: 900;
                color: white;
            }
            .pos .pos-logo img,
            .pos .pos-branding img {
                display: none !important;
            }
        `;
    document.head.appendChild(style);
  },
});
