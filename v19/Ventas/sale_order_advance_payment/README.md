# Pago Adelantado en Orden de Venta

**Versión:** 19.0.1.0.0
**Licencia:** LGPL-3
**Autor:** Alderete Informática

Módulo para Odoo 19 que permite registrar pagos adelantados reales de clientes directamente desde una Orden de Venta confirmada, antes de emitir la factura. El pago se publica como asiento contable real y se aplica automáticamente a la primera factura generada desde esa orden.

---

## Características

- Botón **Registrar Pago Adelantado** en la Orden de Venta confirmada (estado "En Proceso de Venta").
- Crea un `account.payment` real, publicado automáticamente al confirmar el wizard.
- Ribbon visual **"Pendiente de Facturar"** en la orden mientras el pago aún no fue aplicado.
- Aplicación automática por reconciliación contable al publicar la primera factura de la orden.
- Comprobante PDF imprimible (no reemplaza ni es una factura fiscal).
- Pestaña informativa en el formulario de la Orden de Venta y en el formulario de la Factura.
- Sección adicional en el PDF de la factura que indica el adelanto aplicado y el saldo pendiente.
- Compatible con multiempresa.
- Independiente del módulo `sale_op_flow` — los botones se ocultan automáticamente en pedidos del flujo SOF sin crear dependencia entre módulos.

---

## Dependencias

```
sale_management
account
```

No requiere módulos adicionales. La integración con `sale_op_flow` es opcional y se detecta en tiempo de ejecución mediante duck-typing.

---

## Flujo de Uso

```
Orden de Venta confirmada
    │
    ▼
[Botón] Registrar Pago Adelantado
    │
    ▼
Wizard: importe, fecha, diario, método de pago, referencia
    │
    ▼
Se crea account.payment (inbound) → se publica automáticamente
Se crea sale.order.advance.payment (registro de trazabilidad)
    │
    ▼
Orden muestra ribbon "Pendiente de Facturar"
    │
    ▼
[Acción] Crear Factura desde la Orden de Venta
    │
    ▼
Al publicar la factura → reconciliación automática del adelanto
    │
    ▼
Estado del pago adelantado: "Aplicado"
Factura refleja el adelanto en pestaña "Pago Adelantado"
```

---

## Modelos

### `sale.order.advance.payment`

Registro de trazabilidad del pago adelantado. Vincula la orden de venta, el pago contable (`account.payment`) y la factura donde fue aplicado.

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | Char | Referencia automática (`{SO.name}-01`) |
| `sale_order_id` | Many2one | Orden de venta origen |
| `partner_id` | Many2one | Cliente |
| `amount` | Monetary | Importe del adelanto |
| `payment_date` | Date | Fecha del pago |
| `journal_id` | Many2one | Diario contable |
| `payment_id` | Many2one | Pago contable (`account.payment`) |
| `invoice_id` | Many2one | Factura donde se aplicó |
| `state` | Selection | `draft / posted / applied / cancelled` |

### Extensión de `sale.order`

Campos computados agregados:

| Campo | Descripción |
|---|---|
| `advance_payment_id` | Pago adelantado vinculado |
| `advance_payment_count` | Cantidad de pagos adelantados (0 o 1) |
| `advance_payment_amount` | Importe recibido |
| `advance_payment_pending_amount` | Importe pendiente de aplicar |
| `advance_payment_applied_amount` | Importe ya aplicado a factura |
| `advance_payment_estimated_balance` | Saldo estimado (Total - Adelanto) |
| `advance_payment_state` | Estado del pago adelantado |
| `advance_payment_visible` | False en pedidos SOF; True en ventas nativas |

### Extensión de `account.move`

| Campo | Descripción |
|---|---|
| `sale_advance_payment_id` | Pago adelantado aplicado |
| `sale_advance_payment_amount` | Importe aplicado |
| `sale_advance_payment_origin` | Referencia de origen |
| `sale_advance_payment_note` | Notas del pago |

---

## Seguridad

El módulo define el grupo **Pagos Adelantados / Registrar** (`group_advance_payment_user`), que implica el grupo de vendedor (`sales_team.group_sale_salesman`).

Las reglas de acceso sobre `sale.order.advance.payment` siguen el estándar de grupos de Odoo para ventas y contabilidad.

> **Nota:** El campo `category_id` de `res.groups` no se usa — el módulo `simplify_access_management_v19` lo elimina. Solo se usan `name` e `implied_ids`.

---

## Integración con `sale_op_flow`

Los pedidos del flujo SOF (`is_sof_order = True`) no deben mostrar los botones de pago adelantado. Esto se resuelve sin crear dependencia entre módulos:

- El campo `advance_payment_visible` en `sale.order` verifica en tiempo de ejecución si el campo `is_sof_order` existe en el modelo.
- Si `sale_op_flow` está instalado y el pedido es SOF → `advance_payment_visible = False` → botones ocultos.
- Si `sale_op_flow` no está instalado → todos los pedidos muestran los botones normalmente.

```python
has_sof = 'is_sof_order' in self.env['sale.order']._fields
order.advance_payment_visible = not (has_sof and order['is_sof_order'])
```

---

## Reportes

- **Comprobante de Pago Adelantado** (`report_sale_advance_payment`): PDF imprimible desde la Orden de Venta. No es un documento fiscal, es un comprobante interno de recepción del adelanto.
- **Herencia de Factura PDF** (`account_move_report_inherit.xml`): agrega una sección al pie del PDF de la factura indicando el adelanto aplicado y el saldo pendiente.

---

## Limitaciones (v1)

- Solo se permite **un pago adelantado por Orden de Venta**.
- La aplicación automática ocurre solo sobre la **primera factura** publicada que provenga de esa orden.
- No soporta pagos en múltiples monedas distintas a la moneda de la orden.
- La cancelación del adelanto debe realizarse desde Contabilidad (reversión del pago). El estado en la orden se actualiza automáticamente.
