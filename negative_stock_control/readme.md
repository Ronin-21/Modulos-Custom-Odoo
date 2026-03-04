# Control de Stock Negativo (Odoo 18)

**Módulo:** `negative_stock_control`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Inventory  
**Dependencias:** `sale_management`, `stock`, `mrp`

Módulo para **controlar y prevenir operaciones que dejen stock negativo**, bloqueando acciones clave y mostrando un mensaje claro con:

- **Stock disponible**
- **Stock “pronosticado”** (ver nota)
- **Cantidad solicitada / requerida**

---

## ✅ Qué valida / dónde actúa

### 1) Ventas (Orden de Venta)

📌 **Acción:** Confirmar cotización (`sale.order.action_confirm`)  
✅ Valida que cada producto (no servicio) tenga `qty_available` suficiente vs `product_uom_qty`.  
❌ Si falta stock, bloquea la confirmación con un detalle por producto.

---

### 2) Inventario (Órdenes de entrega)

📌 **Acción:** Validar entrega (`stock.picking.button_validate`)  
✅ La intención del módulo es validar entregas **outgoing** antes de validar.

> ⚠️ **Nota importante (estado actual del código):** el módulo define `button_validate()` dos veces para `stock.picking` (una para entregas y otra para traslados internos). Por el orden de carga actual, la validación efectiva queda aplicada al flujo de **traslados internos**, y en entregas **outgoing** la validación puede no ejecutarse (porque el `button_validate()` final solo valida `internal` y para otros tipos hace `return` silencioso).  
> Recomendación: unificar ambas validaciones en un solo override (si querés, lo ajustamos en el módulo).

---

### 3) Inventario (Traslados internos)

📌 **Acción:** Validar traslado interno (`stock.picking.button_validate`)  
✅ Si el picking es de tipo **internal**, valida stock disponible antes de validar.  
❌ Si falta stock, bloquea con detalle por producto.

---

### 4) Fabricación (Órdenes de fabricación)

📌 **Acción:** Confirmar OF (`mrp.production.action_confirm`)  
✅ Valida stock disponible para **insumos** (`move_raw_ids`) antes de confirmar la orden.  
❌ Si faltan insumos, bloquea con detalle por insumo.

---

### 5) Ajustes de inventario (Stock Quants)

📌 **Acción:** Escritura en `stock.quant` (`stock.quant.write`)  
✅ Luego de cada `write`, verifica que el quant no quede con `quantity < 0`.  
❌ Si detecta stock negativo, bloquea con detalle de:

- producto
- cantidad
- ubicación

---

## 🧠 Cómo calcula “stock disponible” y “pronosticado”

- **Stock disponible:** `product.qty_available`
- **“Pronosticado” (mostrado):** `product.virtual_available - product.qty_available`  
  Luego se muestra como `max(0, pronosticado)`.

> Nota: `virtual_available` en Odoo es el stock “forecast” (disponible + entradas - salidas).  
> La diferencia `virtual - qty_available` **no es el forecast total**, sino el “extra” forecast vs lo disponible (útil como pista de entradas/salidas futuras).

---

## 🧪 Cómo probar (checklist rápido)

### A) Venta

1. Producto almacenable con stock en 0.
2. Crear Cotización con cantidad > 0.
3. Confirmar → debe bloquear con “⚠️ STOCK INSUFICIENTE”.

### B) Traslado interno

1. Crear traslado interno de cantidad > stock actual.
2. Validar → debe bloquear con “⚠️ STOCK INSUFICIENTE PARA TRASLADO”.

### C) Fabricación

1. Crear OF con insumos sin stock.
2. Confirmar OF → debe bloquear con “⚠️ STOCK INSUFICIENTE DE INSUMOS”.

### D) Ajuste inventario

1. Intentar dejar un quant con `quantity` negativa.
2. Guardar → debe bloquear con “⚠️ AJUSTE DE INVENTARIO NO PERMITIDO”.

---

## ⚠️ Limitaciones conocidas / recomendaciones

- **No valida por ubicación/almacén:** usa `qty_available` a nivel producto (global por compañía), no el stock exacto de la **ubicación origen** del picking.  
  Si necesitás precisión por ubicación (muy recomendado), se puede mejorar consultando quants por `location_id`.
- **Entregas outgoing pueden no validarse** por el doble override de `button_validate()` (ver sección de entregas).
- **Reserva vs disponibilidad real:** valida contra `qty_available`, no contra “reservado” ni disponibilidad por movimientos ya asignados.
- **`stock.quant.write` es sensible:** se ejecuta en muchas operaciones internas; si tu flujo legítimamente genera quants negativos temporalmente (o tenés políticas de stock negativo habilitadas), puede generar bloqueos.

---

## 📌 Autor

- Abel Acuña
