# Límite de Crédito del Cliente con Aprobación (Odoo 18)

**Módulo:** `customer_credit_limit_approval`  
**Versión:** 18.0.1.0  
**Licencia:** LGPL-3  
**Categoría:** Sales  
**Dependencias:** `sale_management`, `point_of_sale`

Controla el **límite de crédito por cliente** y agrega un **flujo de aprobación** cuando una **Orden de Venta** excede el límite permitido. Además, valida el crédito en **POS** cuando se usa **Cuenta de cliente / Cuenta Corriente (pay later)** y permite **ocultar/mostrar el saldo** de clientes en el selector del POS.

---

## ✅ Funcionalidades principales

### 1) Límite de crédito por cliente (Contactos)

En el cliente (`res.partner`) se agregan:

- **Crédito activo ?** (`credit_check`)
- **Monto de advertencia ?** (`credit_warning`) _(campo disponible; el bloqueo real se hace por el monto de bloqueo)_
- **Monto de bloqueo ?** (`credit_blocking`)

Incluye validaciones:

- No permite montos negativos.
- No permite que _Advertencia_ sea mayor que _Bloqueo_.

---

### 2) Deuda Total (desglose)

El módulo calcula una **Deuda Total** del cliente (`partner.amount_due`) sumando:

1. **Deuda facturada (contable):** `(debit - credit)`
2. **Ventas confirmadas sin facturar:** Órdenes en **Venta** (`state='sale'`) no totalmente facturadas
3. **POS Cuenta Corriente pendiente:** Órdenes de POS con método de pago llamado **“Cuenta Corriente”** y **sin asiento contable** (`account_move = False`)

Campos en la pestaña **Cuenta corriente** del contacto:

- `amount_due_accounting`
- `amount_due_sale`
- `amount_due_pos`
- `amount_due` (total)

> Nota: si no existe un método POS llamado exactamente **“Cuenta Corriente”**, el componente POS queda en 0 y se registra un warning en logs.

---

## 🧾 Flujo en Ventas (Sale Order)

### ¿Cuándo pide aprobación?

Al confirmar una Orden de Venta, si se cumple:

- El cliente tiene **Crédito activo**
- `(Deuda Total del cliente) + (Total de la orden)` **>** `Monto de bloqueo`
- y la orden **no fue aprobada** previamente (`is_credit_limit_final_approved = False`)

Entonces aparece un **wizard** “Límite de Crédito Excedido” con el **exceso** y opción de **Enviar a aprobación**.

---

### Estados agregados a la Orden de Venta

Se agregan estados al `sale.order`:

- **Aprobación de Crédito** (`sales_approval`)
- **Aprobado** (`approved`) _(estado disponible en selección; el flujo usa principalmente el flag de aprobado final)_
- **Rechazado** (`reject`)

---

### Acciones disponibles

#### Enviar a aprobación

- Pasa la orden a `sales_approval`
- Publica nota en chatter
- Notifica (suscribe y mensaje) a usuarios de estos grupos:
  - **ERP Manager** (`base.group_erp_manager`)
  - **Sales Manager** (`sales_team.group_sale_manager`)
  - **System** (`base.group_system`)
- Crea **Actividad** (campanita) para esos managers: “Revisar aprobación de crédito”

#### Aprobar (solo ERP Manager)

- Requiere grupo **ERP Manager**
- Deja la orden en **Enviada** (`sent`)
- Marca `is_credit_limit_final_approved = True`
- Publica nota en chatter
- Notifica a managers
- Crea actividad para el **vendedor**: “Orden aprobada: confirmar venta”

#### Rechazar (solo ERP Manager)

- Requiere grupo **ERP Manager**
- Pasa a `reject`
- Publica nota en chatter
- Notifica a managers
- Crea actividad para el **vendedor**: “Orden rechazada por crédito”

#### Volver a borrador (solo ERP Manager)

- Disponible cuando está en `reject`
- Resetea `is_credit_limit_final_approved = False`

---

### Control de “dueño” de la cotización

El módulo evita que un usuario confirme o envíe a aprobación una orden cuyo **vendedor asignado** (`user_id`) es otro, salvo que sea:

- **Sales Manager**, **ERP Manager** (o equivalentes definidos en el código)

---

## 🧾 Validación en POS (Cuenta de cliente / Cuenta Corriente)

Al sincronizar ventas desde POS (`pos.order.sync_from_ui`), el módulo valida el crédito **solo si**:

- La orden llega en estado `paid`
- Tiene al menos un pago que parezca “Cuenta de cliente”, detectado por:
  - `payment_method.type == 'pay_later'`, o
  - `receivable_account_id` configurada, o
  - flags equivalentes (`use_customer_account`, `is_customer_account`, `allow_credit`)

Si el cliente:

- No tiene **Crédito activo** → bloquea con error pidiendo activar “Crédito activo”.
- Excede el límite → bloquea con un mensaje que muestra:
  - Límite, Deuda Total, Total ticket y Exceso.

> Importante: el cálculo usa **partner.amount_due (Deuda Total)** para que coincida con la lógica de cuenta corriente.

---

## 👁️ Visibilidad del “Saldo” de clientes en POS

### Configuración en Punto de Venta

En `pos.config` se agrega:

- **Mostrar saldo de clientes en POS** (`show_partner_balance`)

Este switch:

- Solo lo pueden ver/cambiar usuarios del grupo:
  - **“POS: Configurar visibilidad de saldos”** (`customer_credit_limit_approval.group_pos_balance_admin`)

### Efecto en la interfaz POS

Cuando `show_partner_balance` está **apagado**, el frontend:

- Oculta la columna **Saldo** del selector de clientes
- Oculta la columna/botón de **acciones** (kebab) en ese listado

(Se implementa con un service que agrega una clase CSS al `<html>` y reglas SCSS.)

---

## 🔐 Seguridad

Incluye accesos para el wizard:

- Usuarios internos (`base.group_user`): leer/crear/escribir wizard (sin borrar)
- ERP Manager (`base.group_erp_manager`): permisos completos sobre el wizard

---

## 📌 Notas técnicas

- Se agrega el campo `accountant_email` en `res.company` (solo campo; no participa del flujo automáticamente).
- El método POS “Cuenta Corriente” se busca por **nombre exacto**: `Cuenta Corriente`.

---
