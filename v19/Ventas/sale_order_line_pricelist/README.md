# Sale Order Line Pricelist — Lista de Precios por Línea de Venta

Módulo custom para **Odoo 19** que permite asignar una lista de precios individual y opcional a cada línea de una orden de venta, independiente de la lista de precios general de la orden.

---

## Funcionalidad

Por defecto, Odoo aplica una única lista de precios a toda la orden. Este módulo agrega un campo **"LP Línea"** en cada línea del pedido que, cuando se completa, hace que esa línea calcule su precio y descuento desde su propia lista de precios en lugar de la general.

| Situación | Comportamiento |
|---|---|
| Línea **sin** LP Línea | Usa la lista general de la orden (estándar Odoo) |
| Línea **con** LP Línea | Usa su propia lista, ignorando la general |
| Cambio de lista general + "Actualizar Precios" | Solo recalcula líneas sin LP Línea propia |
| Lista individual en moneda distinta | Convierte automáticamente a la moneda de la orden |

---

## Instalación

### Requisitos previos

En **Ventas → Configuración → Ajustes**:

- **Listas de precios** → activado (obligatorio)
- **Descuentos** → activado (recomendado, para ver la columna `% de desc.`)

### Pasos

1. Copiar el módulo en la carpeta de addons del servidor
2. Actualizar la lista de módulos (`odoo-update` o reiniciar con `-u all`)
3. Instalar `sale_order_line_pricelist` desde **Ajustes → Módulos**

---

## Uso

### Activar la columna en la grilla

La columna **"LP Línea"** se agrega a la grilla de líneas de la orden. Si no es visible, hacer clic en el ícono de columnas opcionales (⚙) en el encabezado de la tabla y marcarla.

### Asignar una lista de precios a una línea

1. Abrir una cotización o pedido de venta
2. En la grilla de líneas, buscar la columna **"LP Línea"**
3. Seleccionar la lista de precios deseada en la línea correspondiente
4. El precio y el descuento se recalculan automáticamente

### Quitar la lista individual

Borrar el valor del campo **"LP Línea"** en la línea. El precio vuelve a calcularse desde la lista general de la orden.

---

## Comportamiento detallado

### Cálculo de precios

El módulo respeta toda la lógica estándar de listas de precios de Odoo:

- Reglas por producto, categoría y cantidad mínima
- Fórmulas de precio y descuentos
- Fechas de vigencia
- Conversión de moneda automática
- Posición fiscal e impuestos

### Cambio de lista general de la orden

Cuando el usuario cambia la lista de precios general y hace clic en **"Actualizar Precios"**:

- Líneas **sin** LP Línea → se recalculan con la nueva lista general
- Líneas **con** LP Línea → **no se modifican**, conservan su precio calculado desde su lista propia

### Chatter

Cada cambio en el campo **"LP Línea"** queda registrado en el historial de la orden:

> *La línea del producto "Lavarropas XYZ" cambió su lista de precios individual de "Lista Mayorista" a "Lista Especial". Precio recalculado: 45.000,00 ARS.*

Se registra cuando se agrega, cambia o quita una lista individual.

### Facturación

El precio y descuento calculados pasan normalmente a la factura. La lista de precios individual se guarda en la línea de factura (`sale_line_pricelist_id`) solo para trazabilidad interna; no se muestra en pantalla ni en los reportes PDF.

### Duplicación de órdenes

Al duplicar una cotización o pedido, las listas de precios individuales asignadas a cada línea se conservan en la nueva orden.

---

## Seguridad

No se requiere configuración de grupos adicional. Los permisos funcionan así:

| Perfil | Puede seleccionar LP Línea | Puede editar precio manualmente |
|---|---|---|
| Vendedor (`sale.group_sale_salesman`) | ✅ Sí | ❌ No |
| Gerente de ventas (`sales_team.group_sale_manager`) | ✅ Sí | ✅ Sí |
| Administrador (`base.group_system`) | ✅ Sí | ✅ Sí |

Si un usuario sin permisos intenta escribir directamente el precio unitario, Odoo devuelve:

> *"No puede modificar manualmente el precio unitario. Debe cambiar la lista de precios o solicitar autorización a un administrador."*

---

## Alcance

**Aplica a:**
- Cotizaciones
- Pedidos de venta
- Facturas generadas desde ventas (trazabilidad interna)

**No aplica a:**
- Punto de venta (POS)
- eCommerce / Portal
- Compras
- Inventario

---

## Dependencias

```
sale_order_line_pricelist
  ├── sale (Odoo nativo)
  └── account (Odoo nativo)
```

---

## Información técnica

| Campo | Modelo | Tipo | Descripción |
|---|---|---|---|
| `line_pricelist_id` | `sale.order.line` | Many2one → `product.pricelist` | Lista de precios individual de la línea |
| `sale_line_pricelist_id` | `account.move.line` | Many2one → `product.pricelist` | Trazabilidad en factura (readonly, no visible) |

### Métodos principales

- `_get_effective_pricelist()` — devuelve `line_pricelist_id` si existe, sino `order_id.pricelist_id`
- `_compute_pricelist_item_id()` — extendido para usar la lista efectiva de la línea
- `_compute_price_unit()` — fuerza recálculo cuando la línea tiene lista propia
- `_compute_discount()` — usa la lista efectiva para el guard de descuentos
- `_get_update_prices_lines()` en `sale.order` — excluye líneas con lista propia del recálculo masivo

---

## Autor

**Alderete Informática**
Licencia: LGPL-3
Versión: 19.0.1.0.0
