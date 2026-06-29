# sale_invoice_delivery_control

**Compatibilidad:** Odoo 18 SH  
**Versión:** 18.0.1.0.0  
**Categoría:** Sales / Inventory

---

## Descripción

Módulo que controla la relación entre órdenes de venta, facturación, entregas de mercadería y notas de crédito en Odoo 18.

---

## Funcionalidades

### 1. Bloquear entregas sin factura confirmada

Impide validar una entrega de salida de productos almacenables si la orden de venta relacionada **no tiene al menos una factura de cliente publicada (estado `posted`)**.

**Condiciones de aplicación:**
- `picking_type_code == 'outgoing'`
- El picking está vinculado a una `sale.order`
- El picking contiene productos almacenables (`product.type == 'product'` / `is_storable`)
- El parámetro global está habilitado

**No aplica a:**
- Servicios puros
- Pickings sin orden de venta
- Recepciones y transferencias internas
- Facturas en borrador o canceladas (no cuentan como válidas)

**Implementación:** Override de `stock.picking.button_validate()` con `UserError`.  
El bloqueo es backend-safe: funciona desde UI, Inventario, botón inteligente, acciones masivas y RPC.

---

### 2. Advertencia en nota de crédito con mercadería entregada

Muestra una advertencia (sin bloquear) cuando el usuario intenta **publicar una nota de crédito** de cliente relacionada con una orden de venta que ya tiene entregas validadas de productos almacenables.

**Condiciones de aplicación:**
- `move_type == 'out_refund'`
- La NC tiene líneas de productos almacenables
- La factura original está vinculada a una venta con al menos un picking `outgoing` en estado `done`
- El parámetro global está habilitado

**No aplica a:**
- NC de servicios puros
- NC no relacionadas con ventas
- NC sobre facturas de compras
- Contexto `skip_delivery_refund_warning=True` (evita bucles)

**Flujos cubiertos:**
- Publicación directa desde la NC (`action_post`)
- Creación desde el wizard estándar de reversión (`account.move.reversal`)

**Implementación:** Wizard de confirmación `refund.delivery.warning.wizard`.  
El usuario debe hacer clic en **"Confirmar y publicar nota de crédito"** para proceder.

---

## Configuración

Ir a **Ajustes → Control Factura-Entrega:**

| Parámetro | `ir.config_parameter` key | Por defecto |
|-----------|--------------------------|-------------|
| Exigir factura confirmada antes de entregar | `sale_invoice_delivery_control.require_posted_invoice_before_delivery` | `True` |
| Advertir en NC sobre mercadería entregada | `sale_invoice_delivery_control.warn_refund_on_delivered_goods` | `True` |

---

## Casos de prueba

### Caso 1 – Bloqueo de entrega sin factura
1. Crear venta con producto almacenable → Confirmar
2. Intentar validar entrega → **Bloqueado** ✓
3. Crear factura en borrador → Intentar validar → **Bloqueado** ✓
4. Publicar factura → Validar entrega → **Permitido** ✓

### Caso 2 – Venta solo de servicios
1. Crear venta con servicios → Confirmar
2. Validar entrega (si aplica) → **No bloqueado** ✓

### Caso 3 – NC con mercadería entregada
1. Crear venta → Publicar factura → Validar entrega
2. Crear NC sobre la factura → **Advertencia + wizard** ✓
3. Confirmar en el wizard → NC publicada ✓

### Caso 4 – NC sin mercadería entregada
1. Crear venta → Publicar factura → **No validar entrega**
2. Crear NC → **Sin advertencia** ✓

### Caso 5 – NC de servicios
1. Crear factura solo de servicios → Crear NC → **Sin advertencia** ✓

---

## Estructura del módulo

```
sale_invoice_delivery_control/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── res_config_settings.py       # Parámetros globales
│   ├── stock_picking.py             # Bloqueo de entrega
│   ├── account_move.py              # Advertencia en NC (action_post)
│   └── account_move_reversal.py    # Advertencia en NC (wizard reversión)
├── wizards/
│   ├── __init__.py
│   └── refund_delivery_warning_wizard.py  # Wizard de confirmación
├── views/
│   ├── res_config_settings_views.xml
│   ├── account_move_views.xml
│   └── refund_delivery_warning_wizard_views.xml
├── security/
│   └── ir.model.access.csv
└── README.md
```

---

## Dependencias

- `sale_management`
- `sale_stock`
- `stock`
- `account`

---

## Notas técnicas

- **Detección de productos almacenables:** se usa `product.is_storable` (Odoo 18) con fallback a `product.type == 'product'`.
- **Detección de orden de venta:** triple estrategia (líneas → `sale_line_ids`, `invoice_origin`, búsqueda inversa `invoice_ids`).
- **Anti-loop:** contexto `skip_delivery_refund_warning=True` en `action_post` del wizard.
- **Sin modificación de módulos nativos:** herencia limpia (`_inherit`).
- **Control backend:** los bloqueos y advertencias funcionan aunque se oculten o modifiquen botones en la UI.
