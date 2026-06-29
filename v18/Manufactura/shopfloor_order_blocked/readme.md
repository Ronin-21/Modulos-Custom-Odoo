# Control de Dependencias en Órdenes de Trabajo (Shopfloor) — Odoo 18

**Módulo:** `shopfloor_order_blocked`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Manufactura  
**Autor:** Abel Alejandro Acuña — https://ronin-webdesign.vercel.app/  
**Dependencias:** `mrp_workorder`

Este módulo permite **hacer cumplir** las **dependencias entre operaciones** dentro de una Orden de Fabricación: una **orden de trabajo** no podrá iniciarse si depende de otras operaciones que todavía no estén terminadas. Además, valida la **capacidad del centro de trabajo** para evitar iniciar más operaciones simultáneas de las permitidas.

---

## ✅ Funcionalidades

### 1) Bloqueo por dependencias entre operaciones

- Agrega en la **BoM** (`mrp.bom`) el check:
  - **“Controlar dependencias entre operaciones”** (`enforce_workorder_dependency`)
- Si está activo, al intentar **Iniciar** una orden de trabajo (`mrp.workorder.button_start`):
  - Si existen operaciones “bloqueantes” (dependencias) sin finalizar, se bloquea y se muestra un error indicando:
    - Operación actual
    - Lista de operaciones pendientes (nombres)

> La detección se basa en el campo estándar `blocked_by_workorder_ids` (dependencias de workorders).

---

### 2) Validación de capacidad del Centro de Trabajo

Al iniciar una operación, también valida:

- cuántas órdenes de trabajo hay **en progreso** (`state = progress`) en el mismo centro de trabajo
- contra la capacidad configurada (`workcenter.default_capacity`)

Si ya se alcanzó la capacidad, bloquea el inicio con un mensaje detallado.

---

### 3) Re-cálculo al finalizar

Al finalizar una operación (`button_finish`):

- fuerza un recálculo de estado de bloqueo en las workorders dependientes, para que queden disponibles cuando corresponda.

---

## ⚙️ Configuración

1. Ir a **Manufactura → Productos → Listas de materiales (BoM)**
2. Abrir una BoM
3. Asegurarse de tener habilitado el uso de dependencias (campo estándar):
   - **“Permitir dependencias entre operaciones”** (`allow_operation_dependencies`)
4. Activar:
   - ✅ **“Controlar dependencias entre operaciones”**

> El check del módulo aparece **solo** si `allow_operation_dependencies` está activo.

---

## 🧾 Cómo se usa (flujo)

1. En la BoM, configurar las **Operaciones** y sus **dependencias** (operación A bloquea operación B, etc.).
2. Crear una **Orden de Fabricación** y generar las **Órdenes de Trabajo**.
3. En Shopfloor / Órdenes de trabajo:
   - Intentar iniciar una operación “posterior” sin completar las previas → **se bloquea** con mensaje.

---

## 🧪 Prueba rápida

### A) Dependencias

1. Crear 2 operaciones: **Corte** y **Armado**
2. Configurar que **Armado** dependa de **Corte**
3. Crear MO → abrir workorders
4. Intentar iniciar **Armado** sin terminar **Corte** → debe bloquear

### B) Capacidad del Centro de Trabajo

1. En el centro de trabajo, setear `Capacidad` = 1
2. Iniciar una workorder en ese centro
3. Intentar iniciar otra workorder en el mismo centro → debe bloquear

---

## 🧩 Detalles técnicos

### Campos agregados

- `mrp.bom.enforce_workorder_dependency` (Boolean)

### Cómputos informativos (no almacenados)

- `mrp.workorder.is_blocked_by_dependency`
- `mrp.workorder.blocking_workorder_names`

### Assets (debug/UI)

El módulo incluye:

- `static/src/js/workorder_error_handler.js`: patch de `MrpDisplayRecord` (interfaz de Shopfloor) para **loggear** clicks y errores en la consola del navegador.
- `static/src/css/blocked_error.css`: estilos preparados para diálogos de error “blocked” / “workcenter busy”.

> Nota: en esta versión, el JS es principalmente **debug** (console logs) y el CSS aplica si existieran templates/mensajes que incluyan esas clases.

---

## ⚠️ Notas y recomendaciones

- Si querés usarlo en producción, conviene **eliminar o reducir** los `console.log()` del JS para no ensuciar la consola.
- El bloqueo se aplica en backend (`button_start`), por lo que funciona tanto en UI clásica como Shopfloor.

---
