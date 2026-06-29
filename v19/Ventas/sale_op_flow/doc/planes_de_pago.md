# Planes de Pago — Guía de Configuración

Menú: **Flujo de Ventas → Configuración → Planes de pago**

---

## Tipos de plan disponibles

Hay cuatro tipos según los flags del formulario:

| Tipo | `is_pay_later` | `is_check_payment` | Notas |
|---|---|---|---|
| Estándar (efectivo / tarjeta / transferencia) | ✗ | ✗ | Más común |
| Cuenta Corriente (pago diferido) | ✓ | ✗ | No crea pago inmediato |
| Cheque de tercero | ✗ | ✓ | Requiere diario de cheques |
| *(combinación inválida)* | ✓ | ✓ | El sistema lo rechaza |

---

## 1. Efectivo contado

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Efectivo LB` (tipo: Efectivo) |
| Tarjeta / Red | *(vacío)* |
| Cuotas | `1` |
| Tipo de ajuste | `Sin ajuste` |
| Requiere cupón | No |
| Requiere comprobante | No |

**Nombre generado automáticamente:** `Efectivo LB`

---

## 2. Efectivo con descuento

Igual que el anterior, pero con ajuste:

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Efectivo LB` |
| Tipo de ajuste | `Descuento` |
| Porcentaje | `5.00` |
| Producto de ajuste | `Descuento Efectivo` *(producto tipo Servicio)* |

**Nombre generado:** `Efectivo LB · -5.0%`

> El producto de ajuste es obligatorio cuando hay porcentaje > 0. Debe ser de tipo **Servicio**.

---

## 3. Tarjeta de débito

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Tarjetas` (tipo: Banco) |
| Tarjeta / Red | `Visa Débito` |
| Cuotas | `1` |
| Tipo de ajuste | `Sin ajuste` *(o recargo si aplica)* |
| Requiere cupón | `Sí` ← número de cupón de posnet |

**Nombre generado:** `Tarjetas · Visa Débito · 1 pago`

---

## 4. Tarjeta de crédito — 1 pago

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Tarjetas` |
| Tarjeta / Red | `Visa` |
| Cuotas | `1` |
| Tipo de ajuste | `Recargo` |
| Porcentaje | `3.50` |
| Producto de ajuste | `Recargo Financiero` |
| Requiere cupón | `Sí` |

**Nombre generado:** `Tarjetas · Visa · 1 pago · +3.5%`

---

## 5. Tarjeta de crédito — cuotas sin interés (CSI)

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Tarjetas` |
| Tarjeta / Red | `Mastercard` |
| Cuotas | `3` |
| Tipo de ajuste | `Sin ajuste` *(el banco absorbe el costo)* |
| Requiere cupón | `Sí` |

**Nombre generado:** `Tarjetas · Mastercard · 3 cuotas`

---

## 6. Tarjeta de crédito — cuotas con recargo

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Tarjetas` |
| Tarjeta / Red | `Naranja` |
| Cuotas | `6` |
| Tipo de ajuste | `Recargo` |
| Porcentaje | `15.00` |
| Producto de ajuste | `Recargo Financiero` |
| Requiere cupón | `Sí` |

**Nombre generado:** `Tarjetas · Naranja · 6 cuotas · +15.0%`

---

## 7. Transferencia bancaria

| Campo | Valor |
|---|---|
| Diario / Medio de pago | `Banco Santander` (tipo: Banco) |
| Tarjeta / Red | *(vacío)* |
| Cuotas | `1` |
| Tipo de ajuste | `Sin ajuste` |
| Requiere cupón | No |
| Requiere comprobante | `Sí` ← número de transferencia/CBU |

**Nombre generado:** `Banco Santander`

---

## 8. Cuenta Corriente (pago diferido)

Activa el flag **Cuenta Corriente (pago diferido)**. No crea un `account.payment` inmediato — la factura queda abierta con el término de pago indicado.

| Campo | Valor |
|---|---|
| Cuenta Corriente | `Sí` ✓ |
| Término de pago | `30 días` *(o el plazo acordado)* |
| Diario | *(ignorado en el cobro)* |

**Nombre generado:** `Cuenta Corriente · 30 días`

> El pedido puede despacharse aunque la factura quede pendiente de cobro.

---

## 9. Cheque de tercero

Activa el flag **Cheque de tercero**. El cajero debe ingresar número de cheque, banco emisor y fecha de cobro. Requiere el módulo `l10n_latam_check`.

| Campo | Valor |
|---|---|
| Cheque de tercero | `Sí` ✓ |
| Diario / Medio de pago | Diario con método **Cheques de terceros recibidos** habilitado |

**Nombre generado:** `Cheque · Cheques Terceros`

> Verificar en el diario: Configuración → Diarios → pestaña **Pagos entrantes** → agregar método `Cheques de terceros recibidos`.

---

## Campos transversales

### Alcance por empresa (`company_id`)
- **Vacío** → el plan aparece en **todas las empresas / sucursales** (global).
- **Con empresa** → solo visible en esa sucursal.

### Secuencia
Controla el orden en que aparecen los planes en el wizard de cobro. Número menor = aparece primero.

### Producto de ajuste
- Debe ser de tipo **Servicio**.
- Se usa para agregar la línea de descuento/recargo en la factura.
- Puede ser compartido entre planes (ej. un solo producto `Recargo Financiero` para todas las tarjetas con recargo).
- **Obligatorio** si `Tipo de ajuste ≠ Sin ajuste` y `Porcentaje > 0`.

---

## Checklist antes de activar un plan

- [ ] El diario existe y tiene el tipo correcto (Efectivo / Banco)
- [ ] Si tiene ajuste: el producto de ajuste está creado como Servicio
- [ ] Si es cheque: el diario tiene habilitado el método de pago correspondiente
- [ ] Si es Cuenta Corriente: el término de pago está configurado en Odoo
- [ ] `Empresa` configurada según si es global o por sucursal
- [ ] `Secuencia` ordenada para que aparezca en la posición correcta en el cobro
