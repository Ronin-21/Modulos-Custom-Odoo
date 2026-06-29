# Auto Update Cost (Odoo 18)

**Módulo:** `auto_update_cost`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Inventory / Purchase

Automatiza el mantenimiento del **costo del producto** (`standard_price`) y lo **sincroniza entre compañías** según el método de costeo del producto (**Standard** vs **AVCO**), con opciones de actualización por evento (confirmación, recepción o factura) y recálculo opcional de **BoM**.

---

## ✅ Funcionalidades principales

### 1) Productos con costo **Standard**

Permite actualizar el `standard_price` usando una de estas estrategias:

- **Último costo de compra** (`last`)  
  Toma el último costo detectado en el evento configurado (conversión de moneda incluida).

- **Promedio simple** (`avg_simple`)  
  Calcula un promedio **aritmético** de los precios registrados por el módulo (**no ponderado por stock ni por cantidades**).  
  Se guarda por compañía en:
  - `auc_avg_simple_cost`
  - `auc_avg_simple_count`

📌 **Qué costo usa como base:** el módulo calcula costo unitario **CON IVA** como `price_total / qty` (en Orden de Compra o Factura), y luego convierte a la moneda de la compañía destino.

---

### 2) Productos con costo **Promedio (AVCO / average)**

En AVCO, el costo “real” lo calcula Odoo por valorización (stock valuation) al recibir.

Este módulo **NO recalcula** AVCO desde compras/facturas.  
Solo puede:

- **Replicar a otras compañías** el costo promedio real ya calculado por Odoo, **al validar la recepción** (si está habilitado).

---

### 3) Multi-empresa + conversión de moneda

Cuando el alcance es “todas las compañías”, el módulo:

- aplica el costo a cada compañía destino,
- convirtiendo moneda con `currency._convert(...)`,
- y redondeando a **2 decimales**.

---

### 4) Propagación de cambios manuales

Si un usuario edita manualmente el `standard_price` del producto, el módulo puede:

- Propagar el nuevo costo a las otras compañías a las que el usuario tiene acceso.
- Por seguridad, por defecto se propaga solo para **Standard**.
- Para permitirlo también en **AVCO**, debe habilitarse explícitamente (no recomendado).

---

### 5) Recalcular costos por BoM (si MRP está instalado)

Opcionalmente, al cambiar el costo de un componente, el módulo:

- busca BoM donde el componente participa,
- recalcula el costo del producto final (solo si el producto final es **Standard**),
- y publica un mensaje en el chatter con el cambio.

---

## 🔁 Momentos de actualización (Standard)

El módulo puede ejecutar la actualización automática en uno de estos eventos:

- **Al confirmar la Orden de Compra** (`confirm`)
- **Al recibir la mercadería** / validar recepción (`receive`)
- **Al validar la Factura de Proveedor** (`invoice`)

---

## 🧾 Mensajes en chatter

Para auditoría rápida, el módulo registra mensajes en:

- Orden de Compra (si se actualiza en confirmación)
- Picking/Recepción (si se actualiza al recibir)
- Factura de Proveedor (si se actualiza al validar factura)
- Productos finales por BoM (si recalcula BoM)

---

## ⚙️ Configuración

### A) Pantalla de Ajustes (UI)

El módulo agrega un panel en:

**Ajustes → “Precio de Costo Automático”**

Opciones disponibles:

- Activar módulo
- Momento de actualización (Standard)
- Estrategia Standard: último costo / promedio simple
- Alcance multi-empresa: actual / todas
- AVCO: replicar promedio real a sucursales
- Propagar cambios manuales (y permitir AVCO manual)
- Recalcular BoM

> Nota técnica: la vista de Ajustes está implementada sobre campos de `res.company` (`auc_*`).

---

### B) Parámetros del sistema (lo que usa el motor actualmente)

La lógica que actualiza costos lee estos `ir.config_parameter`:

| Clave                                                 | Valores                   | Default   |
| ----------------------------------------------------- | ------------------------- | --------- |
| `auto_update_cost.enabled`                            | `True/False`              | `True`    |
| `auto_update_cost.moment`                             | `confirm/receive/invoice` | `receive` |
| `auto_update_cost.scope`                              | `current/all`             | `all`     |
| `auto_update_cost.standard_strategy`                  | `last/avg_simple`         | `last`    |
| `auto_update_cost.avco_replicate`                     | `True/False`              | `True`    |
| `auto_update_cost.recalc_bom`                         | `True/False`              | `True`    |
| `auto_update_cost.propagate_manual_cost`              | `True/False`              | `False`   |
| `auto_update_cost.propagate_manual_cost_include_avco` | `True/False`              | `False`   |

📌 Si querés controlar el comportamiento con total certeza, configurá estos parámetros en:  
**Ajustes → Técnico → Parámetros → Parámetros del sistema**

---

## 🧠 Cómo calcula el costo (detalle)

### Orden de compra / Recepción (Standard)

- Costo unitario base (con IVA): `purchase_line.price_total / purchase_line.product_qty`
- Ajuste por UoM si corresponde
- Conversión de moneda a la compañía destino
- Redondeo a 2 decimales
- Estrategia:
  - `last`: aplica directo
  - `avg_simple`: actualiza `auc_avg_simple_*` y aplica el promedio

### Factura de proveedor (Standard)

- Costo unitario base (con IVA): `invoice_line.price_total / invoice_line.quantity`
- Ajuste por UoM si corresponde
- Conversión + redondeo
- Misma estrategia `last / avg_simple`

### AVCO (average)

- Usa `standard_price` en la compañía origen (la de la compra/recepción) como “promedio real”
- Lo replica a otras compañías (si está habilitado) al validar la recepción

---

## ⚠️ Consideraciones importantes

- Solo procesa productos tipo **Almacenable** (`product`) y **Consumible** (`consu`). Servicios se ignoran.
- **IVA incluido:** el costo unitario parte de importes con impuestos (`price_total`).
- **Promedio simple no pondera** por stock ni por cantidades: cada evento cuenta como 1 muestra.
- Replicar AVCO entre compañías puede no representar la valorización “real” de cada compañía si cada una gestiona stock/valuación distinta.

---

## 📦 Dependencias

- `purchase`
- `stock`
- `account`
- (Opcional) `mrp` para recálculo de BoM

---

## 👤 Autor / Web

- Autor: Abel Alejandro Acuña
- Web: https://ronin-webdesign.vercel.app/
