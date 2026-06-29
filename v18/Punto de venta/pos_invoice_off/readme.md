# POS - Recibo/Factura desactivado por defecto (Odoo 18)

**Módulo:** `pos_invoice_off`  
**Versión:** 18.0.1.0  
**Licencia:** LGPL-3  
**Categoría:** Point of Sale  
**Dependencias:** `point_of_sale`

Este módulo hace que la opción **“Facturar / To Invoice”** en el Punto de Venta quede **desactivada por defecto** en cada orden nueva.

> No bloquea la facturación: el cajero puede activar manualmente “Facturar” cuando corresponda.

---

## ✅ Qué hace

- Al **crear una nueva orden** en el POS, fuerza `to_invoice = false`.
- Como respaldo, al **entrar a la pantalla de pago**, vuelve a asegurar que la orden esté con `to_invoice` desactivado (por si algo lo pisa).
- En backend, define el campo `pos.order.to_invoice` con `default=False` y asegura en `create()` que, si no viene informado, se guarde como `False`.

---

## 🧠 Cómo funciona (técnico)

### Frontend (POS)

Incluye un patch JS sobre:

- `PosStore.addNewOrder()` (y fallback `add_new_order()` por compatibilidad)
- `PaymentScreen` en `onMounted()`

Archivo:

- `pos_invoice_off/static/src/js/invoice_default_off.js`

Cargado en assets:

- `point_of_sale._assets_pos`

### Backend

Extiende `pos.order`:

- redefine `to_invoice` con `default=False`
- override de `create()` para setear `to_invoice=False` si no vino en `vals`

Archivo:

- `pos_invoice_off/models/pos_order.py`

---

## ⚙️ Instalación

1. Copiar el módulo `pos_invoice_off` en tus addons.
2. Actualizar lista de Apps.
3. Instalar **“POS - Recibo/Factura desactivado por defecto”**.

---

## 🧪 Prueba rápida

1. Abrí una sesión de POS.
2. Creá una orden nueva.
3. Entrá a **Pago**.
4. Verificá que la opción de **Facturar** esté **apagada** por defecto.

---

## ⚠️ Notas

- Si una orden se crea con `to_invoice=True` explícitamente (por lógica propia u otro módulo), este módulo **no lo pisa** en backend (solo fuerza False cuando el valor no viene o viene `None`).
- Si otro módulo vuelve a activar `to_invoice` después, el backup en PaymentScreen intenta re-aplicarlo una vez al montar la pantalla.

---
