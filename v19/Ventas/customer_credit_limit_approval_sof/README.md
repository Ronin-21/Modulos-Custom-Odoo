# Límite de Crédito en Flujo Operativo (puente)

**Versión:** 19.0.1.0.0
**Odoo:** 19
**Licencia:** LGPL-3
**Autor:** Alderete Informática
**Dependencias:** `customer_credit_limit_approval_v19`, `sale_op_flow`

Módulo **puente**. Se instala solo (`auto_install`) cuando están presentes el
módulo de límite de crédito y el flujo operativo de caja. No agrega vistas ni
campos: solo conecta la lógica de ambos en el punto correcto.

---

## Por qué existe

`customer_credit_limit_approval_v19` bloquea el crédito en `sale.order.action_confirm()`.
Pero en `sale_op_flow`, confirmar un pedido sólo lo manda a la cola del cajero:
todavía no se eligió si se cobra en efectivo o en **Cuenta Corriente**. La venta
en cuenta corriente recién se materializa en el **cobro de caja**
(`_complete_multi_payment`, línea con `line_type == 'cc'`).

Sin este puente:
- El bloqueo de crédito dispararía al confirmar (momento equivocado), frenando
  incluso ventas que se van a pagar en efectivo.
- La venta en Cuenta Corriente real, en el cobro, quedaría **sin ningún control**.

---

## Qué hace

1. **Neutraliza** el control de crédito de CLA al confirmar, **sólo** para pedidos
   del flujo operativo (`is_sof_order`). Las ventas estándar siguen con su control
   y flujo de aprobación intactos.

2. **Aplica el control en el cobro**, sólo cuando hay una línea de Cuenta Corriente:

   | Situación del cliente | Resultado |
   |---|---|
   | Sin «Crédito activo» (`credit_check = False`) | 🔴 **Bloqueo duro.** No se puede vender en Cuenta Corriente (el PIN no lo destraba). |
   | Con crédito activo y **no** excede el límite | ✅ Cobro normal. |
   | Con crédito activo y **excede** el límite | 🔑 **Autorización por PIN.** Aparece un wizard que pide el **PIN/NIP de un supervisor**. |

   Al exceder el límite, el cobro se interrumpe con el wizard `ccl.cashier.credit.approval`,
   que pide el **PIN/NIP de un supervisor**. El cajero **no necesita ser supervisor** ni
   cambiar de usuario: el supervisor se acerca y teclea su PIN. Se valida contra
   `hr.employee.pin` de un empleado cuyo usuario pertenece a `sale_op_flow.group_sale_supervisor`.
   Si el PIN es válido, el cobro continúa (contexto `ccl_supervisor_authorized` +
   `ccl_authorized_by_employee_id`) y queda registrado en el chatter **quién** autorizó.

   > **Configuración previa:** cargar el PIN de cada supervisor en
   > **Empleados → (empleado) → Ajustes de RR.HH. → PIN**. Sin PIN cargado, ese
   > supervisor no puede autorizar.

### Cálculo de la deuda proyectada

En el cobro, el pedido SOF ya está confirmado (`state = 'sale'`, sin facturar), por
lo que **ya está incluido** en `partner.amount_due`. Para no contarlo dos veces:

```
deuda_proyectada = partner.amount_due − sale_order.amount_total + monto_cuenta_corriente
```

Es decir: se saca el pedido entero de la deuda y se suma sólo la parte que
realmente va a Cuenta Corriente (lo cobrado en efectivo/banco/cheque no genera deuda).

---

## Limitaciones conocidas

- La autorización valida el PIN contra empleados cuyo usuario está en el grupo
  supervisor. Si dos supervisores comparten el mismo PIN, se registra el primero
  que coincide. Conviene usar PINs únicos.
- El PIN se compara en texto plano (igual que el PIN nativo del POS de Odoo). No
  es un mecanismo criptográfico fuerte; sirve como control operativo de caja.
- El control usa `sale.order.partner_id` (igual que el módulo de crédito), no el
  `commercial_partner_id`. Si se factura a una empresa con contactos hijos, el
  límite se evalúa sobre el contacto del pedido.
- `action_confirm` de CLA mantiene su `ensure_one()`; confirmar varios pedidos SOF
  a la vez no está contemplado (se confirman de a uno en el flujo de caja).
