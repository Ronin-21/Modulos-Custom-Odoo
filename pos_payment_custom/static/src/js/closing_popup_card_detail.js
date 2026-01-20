/** @odoo-module **/

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

function getOrm(self) {
  return self?.orm || self?.env?.services?.orm || null;
}

function getSessionId(self) {
  const pos =
    self?.pos ||
    self?.env?.services?.pos?.pos ||
    self?.env?.services?.pos ||
    null;
  return pos?.pos_session?.id || pos?.session?.id || null;
}

patch(ClosePosPopup.prototype, {
  setup() {
    super.setup();

    // Extender el state con nuestros campos (sin pisar lo existente)
    Object.assign(this.state, {
      card_details_loading: false,
      card_details_groups: [], // [{payment_method_id, payment_method_name, total_amount, total_trans, lines:[...]}]
      card_details_total_amount: 0,
      card_details_total_trans: 0,
    });

    onMounted(() => this.loadCardDetailsByMethod());
  },

  async loadCardDetailsByMethod(force = false) {
    if (this.__ppc_card_details_inflight) return;
    if (this.__ppc_card_details_loaded && !force) return;

    const orm = getOrm(this);
    const sessionId = getSessionId(this);

    if (!orm || !sessionId) return;

    this.__ppc_card_details_inflight = true;
    this.state.card_details_loading = true;

    try {
      const result = await orm.call("pos.session", "get_card_payment_totals", [
        [sessionId],
      ]);

      if (!Array.isArray(result) || !result.length) {
        this.state.card_details_groups = [];
        this.state.card_details_total_amount = 0;
        this.state.card_details_total_trans = 0;
        return;
      }

      const groupsMap = new Map();
      let totalAmount = 0;
      let totalTrans = 0;

      for (const row of result) {
        const methodId = row.payment_method_id;
        const lang =
          this?.env?.services?.session?.user_context?.lang ||
          this?.env?.services?.user?.lang ||
          null;

        const methodName = (() => {
          const v = row.payment_method_name;
          if (!v) return "Método";
          if (typeof v === "string") return v;
          if (typeof v === "object") {
            if (lang && v[lang]) return v[lang];
            if (lang && lang.includes("_")) {
              const short = lang.split("_")[0];
              if (v[short]) return v[short];
            }
            return (
              v.es_AR ||
              v.es ||
              v.en_US ||
              v.en ||
              Object.values(v)[0] ||
              "Método"
            );
          }
          return String(v);
        })();

        if (!groupsMap.has(methodId)) {
          groupsMap.set(methodId, {
            payment_method_id: methodId,
            payment_method_name: methodName,
            lines: [],
            total_amount: 0,
            total_trans: 0,
          });
        }

        const line = {
          card_name: row.card_name || "",
          installment_plan_name: row.installment_plan_name || "",
          installments: Number(row.installments || 1),
          installment_percent: Number(row.installment_percent || 0),
          transaction_count: Number(row.transaction_count || 0),
          total_amount: Number(row.total_amount || 0),
          coupons: row.coupons || "",
        };

        const g = groupsMap.get(methodId);
        g.lines.push(line);
        g.total_amount += line.total_amount;
        g.total_trans += line.transaction_count;

        totalAmount += line.total_amount;
        totalTrans += line.transaction_count;
      }

      this.state.card_details_groups = Array.from(groupsMap.values());
      this.state.card_details_total_amount = totalAmount;
      this.state.card_details_total_trans = totalTrans;

      this.__ppc_card_details_loaded = true;
    } catch (error) {
      console.error(
        "[pos_payment_custom] Error loading card breakdown:",
        error
      );
    } finally {
      this.state.card_details_loading = false;
      this.__ppc_card_details_inflight = false;
    }
  },

  // ✅ NUEVO: Método para descargar reporte 80mm
  async downloadReport80mm() {
    const sessionId = getSessionId(this);

    if (!sessionId) {
      console.error("[pos_payment_custom] No se encontró ID de sesión");

      // Mostrar notificación de error
      if (this.env?.services?.notification) {
        this.env.services.notification.add(
          "Error: No se pudo identificar la sesión actual",
          { type: "danger" }
        );
      }
      return;
    }

    try {
      // Construir URL del reporte
      const baseUrl = window.location.origin;
      const reportUrl = `${baseUrl}/report/pdf/pos_payment_custom.report_saledetails_80mm/${sessionId}`;

      console.log("[pos_payment_custom] Descargando reporte 80mm:", reportUrl);

      // Abrir en nueva pestaña
      const newWindow = window.open(reportUrl, "_blank");

      // Verificar si se bloqueó el popup
      if (
        !newWindow ||
        newWindow.closed ||
        typeof newWindow.closed === "undefined"
      ) {
        console.warn(
          "[pos_payment_custom] Popup bloqueado, intentando descarga directa"
        );

        // Alternativa: Descargar directamente usando fetch
        const response = await fetch(reportUrl);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `ticket_80mm_sesion_${sessionId}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        // Notificación de éxito
        if (this.env?.services?.notification) {
          this.env.services.notification.add(
            "Ticket de 80mm descargado correctamente",
            { type: "success" }
          );
        }
      }
    } catch (error) {
      console.error(
        "[pos_payment_custom] Error al descargar reporte 80mm:",
        error
      );

      // Mostrar notificación de error
      if (this.env?.services?.notification) {
        this.env.services.notification.add(
          "Error al generar el ticket de 80mm. Por favor, intente desde el menú de sesiones.",
          { type: "danger" }
        );
      }
    }
  },
});
