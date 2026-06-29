# Vincular Recepción a Factura (Odoo 18)

**Módulo:** `reception_invoice_link`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Inventory / Accounting  
**Dependencias:** `stock`, `account`

Permite **vincular recepciones de proveedor (stock.picking)** con **facturas de proveedor (account.move)**, con un flujo simple desde Contabilidad y validaciones para evitar errores (proveedor distinto, recepción ya vinculada, etc.). Además, puede **generar líneas de factura automáticamente** a partir de la recepción vinculada.

---

## ✅ Funcionalidades

### 1) Vincular recepciones a una factura de proveedor

Desde una **Factura de Proveedor** (`move_type = in_invoice`) en **borrador**, podés seleccionar una recepción ya realizada:

- Solo muestra recepciones:
  - del **mismo proveedor**
  - tipo **incoming**
  - en estado **Hecho (done)**
  - que **no tengan** otra factura vinculada

La factura guarda las recepciones en:

- `picking_ids` (One2many de recepciones vinculadas)
- `picking_count` (contador)

---

### 2) Smart buttons

- En **Factura de proveedor**: botón **Recepciones** (icono camión)
  - Si hay recepciones vinculadas: abre el listado
  - Si no hay: abre el wizard para elegir una recepción existente

- En **Recepción**: smart button **Factura proveedor**  
  Abre la factura vinculada (si existe).

---

### 3) Generación automática de líneas de factura desde la recepción

Al vincular una recepción, el módulo crea **líneas de factura** (`account.move.line`) desde los movimientos de la recepción:

- Producto: `move.product_id`
- Cantidad: `product_uom_qty` (o `product_qty` como fallback)
- Precio unitario: `product.standard_price`
- Cuenta: `property_account_expense_id` del producto o categoría
- Impuestos: `supplier_taxes_id` (mapeados por posición fiscal del proveedor si aplica)
- Descripción: `move.description_picking` o nombre del producto
- UoM: la del movimiento (`product_uom`) o la del producto
- Marca la línea con `picking_id` para rastrear su origen

> Esto permite saber qué líneas se generaron desde qué recepción.

---

### 4) Quitar recepciones (y sus líneas generadas)

En factura **en borrador**, botón **Quitar recepciones**:

- Desvincula las recepciones (`vendor_invoice_id = False`)
- Elimina las líneas de factura que fueron generadas desde esas recepciones (`line_ids` con `picking_id` correspondiente)

---

### 5) Monto total recepcionado (informativo)

Campo calculado en la factura:

- `reception_amount`: suma **cantidad recepcionada × costo estándar** (`standard_price`) de los productos de las recepciones vinculadas.

> Es un indicador informativo basado en `standard_price` (no necesariamente el precio real de compra).

---

## 🧾 Cómo se usa (flujo recomendado)

1. Ir a **Contabilidad → Proveedores → Facturas**
2. Crear/abrir una **Factura de Proveedor** en **Borrador**
3. Click en:
   - **Agregar recepción** (header), o
   - smart button **Recepciones** (si no hay, te abre el wizard)
4. Elegir una recepción **Hecho (done)** del mismo proveedor
5. Click **Vincular**
6. Se generan líneas en la factura y queda la recepción vinculada

Para deshacer:

- Click **Quitar recepciones** (solo en borrador)

---

## 🔒 Validaciones incluidas

- Solo **facturas de proveedor** pueden tener recepciones vinculadas.
- La recepción y la factura deben ser del **mismo proveedor** (constraint + onchange).
- Una recepción solo puede vincularse a **una** factura (campo `vendor_invoice_id` en `stock.picking`).

---

## ⚠️ Notas importantes / Limitaciones

- **Precio unitario usa `standard_price`:** no toma el precio de compra real de la orden de compra ni el precio de factura del proveedor.
- **Cantidad usa `product_uom_qty` (planificada):** no usa `quantity_done` ni `move_line_ids`. Si necesitás basarlo en cantidad hecha, se ajusta.
- El botón de agregar/quitar está pensado para facturas **en borrador** (la UI lo oculta fuera de borrador). El wizard en sí no valida estado, pero el flujo estándar lo limita desde la vista.

---

## 🧩 Modelo de datos (resumen)

### `account.move` (factura)

- `picking_ids` (One2many) → recepciones vinculadas
- `picking_count` (compute)
- `reception_amount` (compute)

### `stock.picking` (recepción)

- `vendor_invoice_id` (Many2one) → factura proveedor vinculada
- `invoice_reference` (related a `vendor_invoice_id.name`)
- Acción `action_open_vendor_invoice` (smart button)

### `account.move.line`

- `picking_id` (Many2one) → recepción origen de la línea

---

## 👤 Autor

`Tu Empresa`
