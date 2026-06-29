# Límite de Crédito del Cliente con Aprobación

**Versión:** 19.0.1.0.0
**Odoo:** 19
**Licencia:** LGPL-3
**Autor:** Abel Alejandro Acuña — Alderete Informática
**Dependencias:** `sale_management`, `account`

Port a Odoo 19 de la versión completa del módulo (origen: repo `pm-arg-sas`, v18).
Implementa un sistema **propio** de límite de crédito por cliente, paralelo al
nativo de Odoo (cuyo campo en el contacto se oculta para evitar confusión).

---

## Funcionalidades

### Configuración por contacto (pestaña «Cuenta corriente»)
- **Crédito activo** (`credit_check`): activa el control para ese cliente.
- **Monto de advertencia** (`credit_warning`): aviso no bloqueante.
- **Monto de bloqueo** (`credit_blocking`): a partir de acá se bloquea.
- Estado de cuenta en vivo: deuda contable (`credit - debit`), ventas sin
  facturar y **Deuda Total**. Smart button **Estado de Cuenta** (con PDF).

### Control en Órdenes de Venta
Al confirmar (`action_confirm`):
- Si supera el **bloqueo** → wizard de aprobación gerencial (estado `sales_approval`).
- Si supera la **advertencia** (no el bloqueo) → wizard no bloqueante "confirmar igual".
- Estados nuevos: `sales_approval`, `approved`, `reject`.
- Al **aprobar**, la orden se auto-confirma.

### Menú «Crédito» (raíz de Ventas)
- **Órdenes Bloqueadas**: lista de órdenes en aprobación/rechazadas, con
  **aprobar/rechazar masivo** desde la cabecera, columna de **exceso**, búsqueda y
  agrupaciones.
- **Análisis de Crédito**: modelo SQL (`credit.partner.analysis`) con list/pivot/
  graph, utilización %, semáforo (ok / cerca / sobre el límite), accesos directos a
  facturas impagas y órdenes sin facturar.

### Estado de cuenta
- Wizard `credit.statement.wizard` + **reporte PDF** `Estado de Cuenta`
  (facturas abiertas, notas de crédito, órdenes sin facturar, utilización).

---

## Permisos

| Acción | Grupo |
|--------|-------|
| Aprobar / rechazar / volver a borrador crédito | **Aprobador de Límite de Crédito** (`group_credit_approver`) |
| Confirmar SO de otro vendedor | Gerente de Ventas, ERP Manager o Aprobador de Crédito |

---

## Notas de la migración a Odoo 19

- `res.groups.users` → **`user_ids`** (en notificaciones/actividades).
- Grupo: `category_id` → **`privilege_id`** (modelo `res.groups.privilege`).
- Search views: se quitó `<group expand="0">` (inválido en v19); los "Agrupar por"
  van como filtros directos. Validado contra el RNG de v19.
- Vistas lista: `column_invisible` en columnas técnicas.
- **POS fuera de alcance**: la versión v18 traía archivos de Punto de Venta; no se
  portaron. La integración con el flujo de caja `sale_op_flow` va en el módulo
  puente `customer_credit_limit_approval_sof`.
- Se **oculta el límite de crédito nativo** de Odoo (`account.view_partner_property_form`)
  para no confundirlo con este sistema.
- No se portó el xpath sobre `open_customer_statement` (botón de account_followup
  que no existe en el form de partner de v19).

---

## Notas técnicas

- `amount_due` y el desglose son `store=False` (se recalculan al acceder; no usar
  en filtros SQL directos).
- `credit.partner.analysis` es una vista SQL (`_auto = False`) que sólo incluye
  partners con `credit_check = TRUE`.
