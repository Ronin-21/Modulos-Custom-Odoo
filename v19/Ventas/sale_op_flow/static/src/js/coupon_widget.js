/** @odoo-module **/

/**
 * Máscara para Nº Cupón / Voucher del wizard de cobro.
 *
 * Formato permitido: 000-0000
 * - Solo permite dígitos.
 * - Inserta el guión después del tercer dígito.
 * - Limita la carga a 7 dígitos reales.
 *
 * Se implementa por delegación DOM para que funcione aunque Odoo cambie
 * internamente el widget CharField entre versiones. El campo se identifica por:
 *   - class="sof_coupon_mask" en la vista XML, o
 *   - name="coupon_number" en el contenedor generado por Odoo.
 */

function couponDigits(value) {
    return String(value || "").replace(/\D/g, "").slice(0, 7);
}

function formatCoupon(value) {
    const digits = couponDigits(value);
    if (digits.length <= 3) {
        return digits;
    }
    return `${digits.slice(0, 3)}-${digits.slice(3)}`;
}

function isCouponInput(target) {
    if (!(target instanceof HTMLInputElement)) {
        return false;
    }
    return Boolean(
        target.closest(".sof_coupon_mask") ||
        target.closest(".o_field_widget[name='coupon_number']") ||
        target.getAttribute("name") === "coupon_number"
    );
}

function countDigitsBefore(value, position) {
    return String(value || "")
        .slice(0, position || 0)
        .replace(/\D/g, "")
        .length;
}

function cursorPositionForDigitIndex(formatted, digitIndex) {
    if (!digitIndex) {
        return 0;
    }
    let seen = 0;
    for (let index = 0; index < formatted.length; index += 1) {
        if (/\d/.test(formatted[index])) {
            seen += 1;
            if (seen >= digitIndex) {
                return index + 1;
            }
        }
    }
    return formatted.length;
}

function applyCouponMask(input) {
    const previousValue = input.value || "";
    const selectionStart = input.selectionStart || previousValue.length;
    const digitIndex = countDigitsBefore(previousValue, selectionStart);
    const formatted = formatCoupon(previousValue);

    if (previousValue !== formatted) {
        input.value = formatted;
        const newCursor = cursorPositionForDigitIndex(formatted, digitIndex);
        try {
            input.setSelectionRange(newCursor, newCursor);
        } catch (_) {
            // Algunos inputs no permiten setSelectionRange; no es crítico.
        }
    }
}

// Bloquea caracteres no numéricos y evita cargar más de 7 dígitos reales.
document.addEventListener("beforeinput", (event) => {
    const input = event.target;
    if (!isCouponInput(input)) {
        return;
    }

    const inputType = event.inputType || "";
    if (inputType.startsWith("delete") || inputType === "insertFromPaste") {
        return;
    }

    const data = event.data || "";
    if (data && /\D/.test(data)) {
        event.preventDefault();
        return;
    }

    const value = input.value || "";
    const selectedText = value.slice(input.selectionStart || 0, input.selectionEnd || 0);
    const currentDigits = value.replace(/\D/g, "").length;
    const selectedDigits = selectedText.replace(/\D/g, "").length;
    const incomingDigits = data.replace(/\D/g, "").length;

    if (currentDigits - selectedDigits + incomingDigits > 7) {
        event.preventDefault();
    }
}, true);

// Normaliza tipeo y pegado antes de que Odoo tome el valor del campo.
document.addEventListener("input", (event) => {
    const input = event.target;
    if (!isCouponInput(input)) {
        return;
    }
    applyCouponMask(input);
}, true);

// Asegura que al salir del campo quede normalizado.
document.addEventListener("change", (event) => {
    const input = event.target;
    if (!isCouponInput(input)) {
        return;
    }
    applyCouponMask(input);
}, true);
