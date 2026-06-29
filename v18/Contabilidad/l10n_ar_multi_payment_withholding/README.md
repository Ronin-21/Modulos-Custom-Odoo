# l10n_ar_withholding_usability

**Versión:** 18.0.1.0.0  
**Autor:** Alderete Informática  
**Licencia:** LGPL-3  
**Dependencias:** `l10n_ar_withholding`, `l10n_latam_check`

---

## Descripción

Módulo complementario para la localización argentina de retenciones en pagos (`l10n_ar_withholding`). Agrega mejoras funcionales orientadas a la operatoria real de empresas argentinas, donde los importes de retención pueden diferir del cálculo automático y los pagos suelen combinarse con múltiples medios de pago.

---

## Funcionalidades

### 1. Importe de retención editable

En el wizard de registro de pagos, la columna **Cantidad** de la tabla de retenciones es editable. El sistema calcula el importe automáticamente según el impuesto configurado, pero el usuario puede pisarlo manualmente para ajustarlo al comprobante recibido del cliente.

**Comportamiento:**

- Al abrir el wizard, la columna muestra el cálculo automático.
- El usuario puede modificar el importe libremente.
- El valor manual se respeta en el asiento contable generado.
- Si se cambia el impuesto, el importe vuelve al cálculo automático.

**Caso de uso típico:** el cliente entrega una orden de pago con un importe de retención que difiere por centavos o por redondeo del cálculo del sistema.

---

### 2. Múltiples métodos de pago

Permite registrar un pago combinando distintos medios (transferencia bancaria, cheques de terceros, efectivo, etc.) en una sola operación que cancela la factura completa.

**Cómo usarlo:**

1. Abrir el wizard de pago desde una factura.
2. Activar el checkbox **"Utilice múltiples métodos de pago"**.
3. El sistema pre-carga una línea con el diario y método actual.
4. Agregar o modificar las líneas necesarias hasta que la **Diferencia** sea $0,00.
5. Si alguna línea usa cheques, completar la pestaña **Cheques**.
6. Hacer clic en **Crear pago**.

**Resultado contable:**

- Se genera un pago separado por cada línea de método de pago.
- Las retenciones se registran en un asiento de ajuste independiente en el diario "Operaciones varias".
- Todos los movimientos quedan reconciliados contra la factura original.

**Restricciones:**

- La suma de las líneas de pago debe coincidir con el neto de la factura (total menos retenciones).
- Se permite una sola línea por tipo de cheque (nueva vs. existente), pero se pueden usar ambos tipos simultáneamente.

---

### 3. Resumen de retenciones en el wizard

Debajo de la tabla de retenciones se muestra un bloque informativo con:

| Campo                          | Descripción                                            |
| ------------------------------ | ------------------------------------------------------ |
| Total documento / pago base    | Importe total de la factura a cancelar                 |
| Total retenciones              | Suma de todas las retenciones (manuales o automáticas) |
| Importe real del medio de pago | Neto que debe cubrir el/los medios de pago             |
| Importe de cheques             | Solo visible cuando el método incluye cheques          |

---

### 4. Resumen de retenciones en el pago registrado

Una vez confirmado el pago, la vista del comprobante muestra el mismo resumen con los valores finales aplicados.

---

## Notas técnicas

- El campo `x_manual_amount_value` en `l10n_ar.payment.register.withholding` almacena el importe manual ingresado por el usuario. El campo `amount` (compute) se sincroniza con este valor justo antes de que el módulo base genere el asiento.
- El modelo `l10n_ar.payment.register.multi.line` gestiona las líneas del multi-pago como un `TransientModel` asociado al wizard `account.payment.register`.
- Al activar o desactivar el multi-pago, todas las líneas y cheques cargados se limpian para garantizar un estado consistente.

---

## Casos probados

- ✅ Pago simple con un solo método de pago y retenciones manuales
- ✅ Pago simple con cheque y retenciones manuales
- ✅ Multi-pago con banco + cheque + efectivo
- ✅ Multi-pago con cheque existente + cheque nuevo simultáneos
- ✅ Pago de múltiples facturas agrupadas
- ✅ Factura con saldo $0,00 al finalizar en todos los casos
