# Posición Fiscal Automática por Diario

## ¿Qué es y para qué sirve?

El campo **"Posición Fiscal Automática"** (`prs_fiscal_position_id`) en el diario permite que *toda factura creada con ese diario* reciba automáticamente una posición fiscal determinada, sin importar desde qué módulo o flujo se genere la factura (SOF, Ventas nativo, Contabilidad directa).

### Caso de uso principal: Ventas No Fiscales

Los diarios de tipo **"Auto CL / Auto LB / Auto YY…"** (sin ARCA, sin documentos) se usan para comprobantes internos que no van a la AFIP. En estos casos:

- El cliente recibe un precio final sin discriminación de IVA.
- Internamente **no se quiere registrar IVA** (el precio ya es el precio final).
- Se necesita que esto funcione igual desde SOF que desde Ventas nativo.

La solución es una **Posición Fiscal "Venta No Fiscal"** configurada en esos diarios.

---

## Paso 1: Crear la Posición Fiscal

Ir a **Contabilidad → Configuración → Posiciones Fiscales → Nuevo**

| Campo | Valor |
|---|---|
| Nombre | `Venta No Fiscal` |
| Empresa | *(dejar vacío para que aplique a todas, o elegir empresa)* |
| Auto detección | No (no marcar ninguna condición automática) |

### Mapeo de impuestos

En la pestaña **"Impuestos"**, agregar una línea por cada impuesto de venta:

| Impuesto origen | Impuesto destino |
|---|---|
| IVA 21% | *(dejar vacío = eliminar el impuesto)* |
| IVA 10.5% | *(dejar vacío)* |
| IVA 27% | *(dejar vacío)* |

> **Importante**: dejar "Impuesto destino" en blanco elimina el impuesto de la transacción.
> El precio del producto se convierte en el precio final: no hay base + IVA, solo precio total.

Guardar.

---

## Paso 2: Configurar el Diario

Ir a **Contabilidad → Configuración → Diarios** → abrir el diario no-fiscal (ej. "Auto CL").

Pestaña **"Configuración avanzada"** → sección **"Posición Fiscal Automática"**:

- Campo: `Posición fiscal automática`
- Seleccionar: `Venta No Fiscal`

Guardar.

Repetir para cada diario no-fiscal: Auto CL, Auto LB, Auto YY, Auto PI, Auto ARB, Auto ST.

---

## Paso 3: Verificar

Crear una factura o un pedido de venta usando ese diario. Verificar que:

1. La factura tiene `fiscal_position_id = Venta No Fiscal` automáticamente.
2. Las líneas de la factura **no tienen impuesto** aplicado.
3. El total = precio del producto (sin desglose de IVA).
4. El PDF impreso muestra solo el total, sin líneas de IVA.

---

## Comportamiento técnico

El campo actúa en dos puntos del ciclo de vida de la factura:

1. **Creación programática** (`create()`): si el `journal_id` tiene `prs_fiscal_position_id` y no viene un `fiscal_position_id` explícito en los valores, se inyecta antes de crear la factura. Las líneas que se agreguen después heredarán el mapeo de impuestos.

2. **UI** (`onchange journal_id`): cuando el usuario cambia el diario en el formulario, la posición fiscal se aplica automáticamente si no hay una ya seleccionada.

### Prioridad

- Si la factura ya tiene una posición fiscal asignada (desde el pedido de venta o manual), **no se sobreescribe**.
- El diario solo inyecta la posición cuando el campo está vacío.

### ¿Afecta facturas de compra?

Solo si el diario de compras también tiene `prs_fiscal_position_id` configurado. Por defecto los diarios de compra no tienen este campo configurado.

---

## Diferencia con "Posición Fiscal del Cliente"

| | Posición fiscal del cliente | Posición fiscal del diario |
|---|---|---|
| **Dónde se configura** | En el contacto (res.partner) | En el diario contable |
| **Cuándo aplica** | Solo para ese cliente | Para todo comprobante del diario |
| **Prioridad** | Más baja | Más alta (sobreescribe la del cliente si la factura no tiene una aún) |
| **Caso de uso** | Cliente exento específico | Diario completo no-fiscal / categoría |
