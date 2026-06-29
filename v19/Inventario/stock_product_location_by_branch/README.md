# Ubicaciones de Producto por Sucursal

**Versión:** 19.0.1.0.0  
**Licencia:** LGPL-3  
**Dependencias:** `stock`, `purchase`, `purchase_stock`

---

## ¿Qué hace este módulo?

Permite definir, para cada **producto + almacén/sucursal**, una **ubicación interna habitual**. Una vez configurada, el módulo aplica esa ubicación automáticamente en:

- Recepciones de órdenes de compra
- Transferencias internas entre sucursales

Además controla que los ajustes de inventario respeten esa configuración, evitando que el stock quede en ubicaciones incorrectas por error del operador.

---

## Características

| Función | Descripción |
|---|---|
| Maestro de ubicaciones | Define Empresa + Almacén + Producto → Ubicación habitual |
| Auto-ubicación en recepciones | Al confirmar una recepción, asigna el destino correcto a cada línea |
| Auto-ubicación en transferencias internas | Al confirmar una transferencia, asigna origen y destino según la config |
| Transferencia inter-sucursal | Wizard que crea dos albaranes vinculados con ubicación de tránsito |
| Preparación de inventario físico | Genera los quants necesarios para contar solo los productos configurados |
| Importación masiva desde CSV/Excel | Carga inicial de stock y configuraciones desde un archivo |
| Validación en ajustes de inventario | Bloquea ajustes que agreguen stock en ubicaciones incorrectas |

---

## Configuración inicial

### 1. Acceder al maestro de ubicaciones

`Inventario → Configuración → Ubicaciones por Producto/Sucursal`

Cada registro relaciona:

- **Empresa / Sucursal** — la empresa del almacén
- **Almacén** — la sucursal donde vive el producto
- **Producto** — debe ser un producto almacenable
- **Ubicación habitual** — ubicación interna dentro de ese almacén

> La ubicación debe pertenecer jerárquicamente al almacén seleccionado. El módulo valida esto al guardar.

### 2. Parámetros globales

`Inventario → Configuración → Ajustes → sección "Ubicaciones por Sucursal"`

| Parámetro | Por defecto | Descripción |
|---|---|---|
| Aplicar en recepciones de compra | Activado | Auto-asigna destino al confirmar recepciones |
| Aplicar en transferencias internas | Activado | Auto-asigna origen y destino en transferencias internas |
| Si falta configuración | Advertencia | `Advertencia`: deja la ubicación estándar y registra un aviso en el chatter. `Bloquear`: impide confirmar el albarán. |
| Aplicar en líneas de operación | Activado | Actualiza también las líneas de detalle (`stock.move.line`), no solo el movimiento |

---

## Flujos principales

### Recepción de compra

1. Se crea una orden de compra y se genera la recepción.
2. Al confirmar la recepción (`Validar` → `action_confirm`), el módulo busca la ubicación habitual para cada producto en el almacén destino.
3. Si la encuentra, sobreescribe `location_dest_id` del movimiento (y sus líneas si está activada la opción).
4. Si no la encuentra, actúa según el parámetro "Si falta configuración".

### Transferencia interna entre sucursales

#### Opción A — Wizard "Transferencia entre Sucursales"

`Inventario → Configuración → Transferencia entre Sucursales`

1. Seleccionar sucursal origen y destino.
2. Agregar los productos con sus cantidades.
3. Al crear, el módulo genera **dos albaranes confirmados**:
   - **Salida:** `Ubicación origen → Tránsito Inter-Sucursal`
   - **Entrada:** `Tránsito Inter-Sucursal → Ubicación destino`
4. Validar primero el albarán de salida (desde la sucursal origen) y luego el de entrada (desde la sucursal destino).

> Las ubicaciones de cada albarán se calculan desde la configuración del módulo. Si un producto no tiene configuración, se usa `lot_stock_id` del almacén como fallback.

#### Opción B — Transferencia interna estándar de Odoo

Al confirmar cualquier transferencia interna (`picking_type_code = 'internal'`), el módulo aplica automáticamente la ubicación habitual para el origen (almacén de la ubicación fuente) y el destino (almacén de la ubicación destino).

---

## Ajustes de inventario

El módulo intercepta `_apply_inventory()` para validar que el stock se coloque en la ubicación correcta.

### Reglas de validación

| Situación | diff > 0 | diff = 0 | diff < 0 |
|---|---|---|---|
| Producto con config, ubicación correcta | ✅ Permitido | ✅ Permitido | ✅ Permitido |
| Producto con config, **ubicación incorrecta** | ❌ Bloqueado | ❌ Bloqueado | ✅ Permitido |
| Producto **sin config** en ese almacén | ❌ Bloqueado | ❌ Bloqueado | ✅ Permitido |
| Ubicación virtual / sin almacén asignado | ✅ Ignorado | ✅ Ignorado | ✅ Ignorado |
| Producto no almacenable | ✅ Ignorado | ✅ Ignorado | ✅ Ignorado |

> Las reducciones (`diff < 0`) se permiten siempre para poder corregir stock que haya quedado en ubicaciones incorrectas.

**Mensaje de error cuando se bloquea:**

```
No se puede aplicar el ajuste de inventario.

Los siguientes productos no tienen ubicación habitual configurada para su almacén:
• Electroválvula 2 Vías Ariston  (almacén: LINEA BLANCA)

Los siguientes productos están siendo ubicados en una posición diferente a la habitual:
• Electroválvula Triple Ariston
  Ajuste en:    DP-AR/Existencias/1er Piso/Pasillo 4 - Sector A
  Habitual:     Deposito Principal/Existencias
  Almacén:      LINEA BLANCA

Configurá las ubicaciones en:
Inventario → Configuración → Ubicaciones por Producto/Sucursal
```

---

## Herramientas de carga inicial

### Preparar inventario físico desde la configuración

`Inventario → Configuración → Preparar Ajuste de Inventario` *(o desde la vista del maestro)*

Genera los quants necesarios en las ubicaciones configuradas para que el operador solo tenga que completar la columna "Contado". Útil al iniciar operaciones.

1. Seleccionar empresa y opcionalmente filtrar por almacén.
2. El wizard muestra cuántos quants se crearán vs. cuántos ya existen.
3. Al confirmar, abre directamente la vista de Inventario Físico filtrada a esos quants.

### Importación masiva desde CSV/Excel

`Inventario → Configuración → Importar Inventario desde CSV/Excel`

Permite cargar el stock inicial de múltiples productos de una vez.

**Formato del archivo (3 columnas):**

| Codigo | Ubicacion | Cantidad |
|---|---|---|
| 00208087 | DP-CO/Existencias/Pasillo 1 - Sector A | 5 |
| KC2106HSB | DP-CO/Existencias/Pasillo 2 - Sector B | 12 |

- **Codigo:** código interno del producto (`default_code`) o nombre exacto. También acepta external IDs de Odoo.
- **Ubicacion:** nombre completo de la ubicación (`complete_name`) o nombre simple.
- **Cantidad:** cantidad contada. Acepta coma o punto como separador decimal.

El wizard descarga una plantilla `.xlsx` de ejemplo desde el botón "Descargar Plantilla".

**Al importar, el wizard:**
1. Crea la configuración en `stock.product.branch.location` si no existe.
2. Crea o actualiza el quant en la ubicación indicada con la cantidad contada.
3. Muestra un resumen con los resultados y errores fila por fila.
4. Abre el Inventario Físico filtrado a los quants procesados para revisión y aplicación.

> La importación no aplica el ajuste automáticamente. El operador debe revisar y aplicar desde el Inventario Físico.

---

## Botón manual en albaranes

En cualquier albarán de recepción o transferencia interna en estado confirmado/listo, aparece el botón **"Aplicar Ubicaciones Automáticas"** en la cabecera. Permite re-aplicar las ubicaciones habituales si se agregaron líneas después de confirmar o si se hicieron correcciones manuales.

También existe el checkbox **"Desactivar ubicaciones automáticas"** (en la pestaña Información Adicional) para exceptuar albaranes puntuales de la lógica automática.

---

## Notas técnicas

- El módulo usa `parent_path` de `stock.location` para determinar a qué almacén pertenece una ubicación, sin depender de campos adicionales.
- Los albaranes creados por el wizard inter-sucursal tienen `splb_disable_auto = True` para evitar que el hook de auto-ubicación interfiera (el wizard ya calculó las ubicaciones correctas).
- La validación de ajustes de inventario opera en `stock.quant._apply_inventory()`, el único punto que Odoo ejecuta siempre al confirmar un ajuste, independientemente del origen (UI, API, o wizard).
- El módulo no modifica rutas de abastecimiento, reglas de reordenamiento ni picking types existentes.
