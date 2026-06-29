/** @odoo-module **/

import { MrpDisplayRecord } from "@mrp_workorder/mrp_display/mrp_display_record";
import { patch } from "@web/core/utils/patch";

console.log("========================================");
console.log("✅ PATCH DE MrpDisplayRecord CARGADO");
console.log("========================================");

patch(MrpDisplayRecord.prototype, {
  setup() {
    console.log("🔧 [MrpDisplayRecord SETUP] Ejecutándose...");
    super.setup();
    console.log("✅ [MrpDisplayRecord SETUP] Completado");
  },

  async onClickDone(...args) {
    console.log("✅ [onClickDone] ¡BOTÓN 'MARCAR COMO HECHA' PRESIONADO!");
    console.log("📦 [onClickDone] Args:", args);

    try {
      const result = await super.onClickDone(...args);
      console.log("✅ [onClickDone] Éxito");
      return result;
    } catch (error) {
      console.log("❌ [onClickDone] Error capturado:", error);
      console.log(
        "📝 [onClickDone] Mensaje:",
        error?.data?.message || error?.message
      );
      throw error;
    }
  },

  async onClickValidate(...args) {
    console.log("✅ [onClickValidate] ¡BOTÓN VALIDAR PRESIONADO!");
    console.log("📦 [onClickValidate] Args:", args);

    try {
      const result = await super.onClickValidate(...args);
      console.log("✅ [onClickValidate] Éxito");
      return result;
    } catch (error) {
      console.log("❌ [onClickValidate] Error:", error);
      console.log(
        "📝 [onClickValidate] Mensaje:",
        error?.data?.message || error?.message
      );
      throw error;
    }
  },

  async onClickStart(...args) {
    console.log("▶️ [onClickStart] ¡BOTÓN INICIAR PRESIONADO!");
    console.log("📦 [onClickStart] Args:", args);

    try {
      const result = await super.onClickStart(...args);
      console.log("✅ [onClickStart] Éxito");
      return result;
    } catch (error) {
      console.log("❌ [onClickStart] Error capturado:", error);
      console.log(
        "📝 [onClickStart] Mensaje:",
        error?.data?.message || error?.message
      );
      throw error;
    }
  },

  async doAction(...args) {
    console.log("🎯 [doAction] Ejecutándose");
    console.log("📦 [doAction] Args:", args);

    try {
      const result = await super.doAction(...args);
      console.log("✅ [doAction] Éxito");
      return result;
    } catch (error) {
      console.log("❌ [doAction] Error:", error);
      throw error;
    }
  },

  async save(...args) {
    console.log("💾 [save] Ejecutándose");
    console.log("📦 [save] Args:", args);

    try {
      const result = await super.save(...args);
      console.log("✅ [save] Éxito");
      return result;
    } catch (error) {
      console.log("❌ [save] Error:", error);
      throw error;
    }
  },
});

console.log("========================================");
console.log("✅ PATCH MrpDisplayRecord REGISTRADO");
console.log("========================================");
