# payment_register_statement_card_v19

Módulo de cobros con tarjeta para Odoo 19. Agrega soporte para tarjetas de crédito/débito con planes de cuotas, comisiones, retenciones y acreditación automática o manual en el diario bancario destino.

---

## Índice

1. [Conceptos clave](#conceptos-clave)
2. [Configuración del diario puente (tarjetas)](#configuración-del-diario-puente-tarjetas)
3. [Configuración del banco receptor](#configuración-del-banco-receptor)
4. [Cuentas contables recomendadas](#cuentas-contables-recomendadas)
5. [Configuración de tarjetas y procesadores](#configuración-de-tarjetas-y-procesadores)
6. [Flujo contable completo](#flujo-contable-completo)
7. [Jerarquía de configuración](#jerarquía-de-configuración)
8. [Control de acreditaciones](#control-de-acreditaciones)

---

## Conceptos clave

El módulo opera con dos diarios separados:

| Diario | Rol | Ejemplo |
|---|---|---|
| **Diario puente** | Recibe el pago bruto al momento de la venta | Tarjetas Clover |
| **Banco receptor** | Recibe el neto acreditado por el procesador | Banco Santander |

El dinero transita por una **cuenta de transferencia** (liquidez interna) que balancea a $0 al finalizar la acreditación.

---

## Configuración del diario puente (tarjetas)

Este diario actúa como intermediario. El dinero llega acá al registrar el pago y sale cuando se ejecuta la acreditación.

### Pestaña "Asientos contables"

| Campo | Valor recomendado |
|---|---|
| Tipo | Banco |
| Cuenta | Cuenta puente exclusiva para tarjetas (ej. `1.1.1.02.010 Tarjetas a acreditar`) |

> La cuenta configurada aquí es la que el sistema usa para reconciliar el pago original con la línea de acreditación. Es crítico que sea la misma cuenta tanto en el pago como en el extracto de acreditación.

### Pestaña "Pagos entrantes"

| Campo | Valor recomendado |
|---|---|
| Método de pago | Pago manual |
| Cuentas de recibos pendientes | **La misma cuenta** configurada en "Asientos contables" |

> Esto es obligatorio. Si la cuenta de recibos pendientes difiere de la cuenta del diario, el asiento del pago (PBNK) usará una cuenta distinta y la reconciliación durante la acreditación fallará silenciosamente.

### Pestaña "Tarjetas PRS"

| Campo | Valor |
|---|---|
| Procesador de tarjetas | El procesador correspondiente (ej. CLOVER) |
| Control de acreditaciones | Desactivado (el control se pone en el banco receptor) |
| Cuenta comisiones | Opcional — si se deja vacío usa la cuenta predeterminada de la empresa |
| Cuenta IVA comisión | Opcional |
| Cuenta retenciones | Opcional |

### Campos que NO se deben activar

| Campo | Motivo |
|---|---|
| Flujo de Pagos (`prs_payment_register_enabled`) | El flujo de tarjetas lo genera el módulo internamente; activarlo crea entradas redundantes |
| Creación automática de extractos (`auto_extract_enabled`) | La acreditación crea su propio extracto; este flag genera un BNK duplicado que rompe la reconciliación |

---

## Configuración del banco receptor

Este es el diario bancario donde el procesador deposita el neto (bruto menos comisiones y retenciones).

### Pestaña "Asientos contables"

| Campo | Valor |
|---|---|
| Tipo | Banco |
| Cuenta | Cuenta bancaria real (ej. `1.1.1.01.002 Banco Santander cta. cte.`) |

### Pestaña "Pagos entrantes / salientes"

No requiere configuración especial para la acreditación de tarjetas. La acreditación crea una línea de extracto bancario directamente, no un pago, por lo que la cuenta de recibos pendientes no interviene en este flujo.

### Pestaña "Tarjetas PRS"

| Campo | Descripción |
|---|---|
| Control de acreditaciones | Ver sección [Control de acreditaciones](#control-de-acreditaciones) |
| Cuenta comisiones | Sobreescribe la cuenta predeterminada de la empresa solo para este banco |
| Cuenta IVA comisión | Ídem |
| Cuenta retenciones | Ídem |

---

## Cuentas contables recomendadas

### Cuenta puente de tarjetas

- **Tipo**: Activo corriente (`asset_current`)
- **Reconciliable**: Sí (obligatorio)
- **Ejemplo**: `1.1.1.02.010 Tarjetas a acreditar`
- **Uso**: Cuenta del diario puente. Acumula el bruto de las ventas con tarjeta hasta que se ejecuta la acreditación.

### Cuenta de transferencia (liquidez interna)

- **Tipo**: Activo corriente (`asset_current`)
- **Reconciliable**: Sí (obligatorio)
- **Ejemplo**: `6.0.00.00.01 Transferencias internas` (cuenta de tránsito de Odoo)
- **Uso**: Puente contable entre el diario puente y el banco receptor. Su saldo debe ser siempre $0 al finalizar cada acreditación.
- **Nota**: Odoo usa la cuenta configurada en Ajustes → Contabilidad → "Transferencia de liquidez". Si no está configurada, el módulo la busca automáticamente.

### Cuenta de comisiones

- **Tipo**: Gasto (`expense`)
- **Ejemplo**: `5.6.1.01.081 Comisiones bancarias por tarjetas`
- **Uso**: Se debita por el importe de la comisión del procesador en cada acreditación.

### Cuenta de IVA sobre comisiones

- **Tipo**: Activo corriente (`asset_current`) o Gasto (`expense`)
- **Ejemplo Argentina**: `1.1.4.04.010 IVA crédito fiscal — servicios financieros`
- **Uso**: IVA que factura el procesador sobre su comisión. Si es IVA crédito fiscal recuperable, usar activo corriente. Si no es recuperable, usar gasto.

### Cuenta de retenciones / percepciones

- **Tipo**: Activo corriente (`asset_current`) o Pasivo corriente (`liability_current`)
- **Ejemplo Argentina (IIBB percepción)**: `1.1.4.04.030 Retenciones y percepciones a recuperar`
- **Uso**: Retenciones que el procesador practica sobre la liquidación. Generalmente un activo a recuperar contra IIBB o Ganancias.

### Dónde configurar las cuentas predeterminadas

`Ajustes → Contabilidad → Cobros con Tarjeta`

Estas cuentas aplican a todos los diarios puente que no tengan cuentas propias configuradas. Se pueden sobreescribir por diario en la pestaña "Tarjetas PRS" de cada journal.

---

## Configuración de tarjetas y procesadores

### Procesador de tarjetas (`prs.card.provider`)

Agrupa los valores por defecto para todas sus tarjetas. Se accede desde `Configuración → Cobros con Tarjeta → Procesadores`.

| Campo | Descripción |
|---|---|
| Diario de acreditación | Banco receptor donde deposita este procesador |
| Días de acreditación | Plazo estándar del procesador |
| Tipo de días | Corridos o hábiles |
| Comisión (%) | Porcentaje de comisión base |
| IVA comisión (%) | IVA sobre la comisión |
| Retención (%) | Retención/percepción aplicada |

### Tarjeta (`account.card`)

Hereda los valores del procesador. Puede sobreescribir cualquier campo. Si se deja `company_id` vacío, la tarjeta es **global** y está disponible en todas las empresas (indicado con el ribbon celeste "Global").

### Plan de cuotas (`account.card.installment`)

Tiene la mayor prioridad en la jerarquía. Permite diferencias de comisión, días o diario entre planes del mismo tipo de tarjeta.

---

## Flujo contable completo

### Al registrar el pago (venta con tarjeta)

```
DR  1.1.1.02.010  Tarjetas a acreditar     $ 1.000,00
    CR  1.1.3.01.001  Cuentas por cobrar       $ 1.000,00
```

Simultáneamente se crea un registro `prs.money.flow` de tipo `card_settlement` con la fecha de acreditación calculada según los días configurados.

### Al ejecutar la acreditación

**Paso 1 — Extracto en el diario puente (salida del bruto)**
```
DR  6.0.00.00.01  Transferencias internas  $ 1.000,00
    CR  1.1.1.02.010  Tarjetas a acreditar     $ 1.000,00
```
Reconcilia con el PBNK original → la cuenta puente queda en cero.

**Paso 2 — Extracto en el banco receptor (entrada del neto)**
```
DR  1.1.1.01.002  Banco Santander cta. cte.   $   950,00
    CR  6.0.00.00.01  Transferencias internas      $   950,00
```

**Paso 3 — Asiento de comisión**
```
DR  5.6.1.01.081  Comisiones bancarias         $    42,00
DR  1.1.4.04.010  IVA crédito fiscal           $     8,00
    CR  6.0.00.00.01  Transferencias internas      $    50,00
```

**Resultado final de la cuenta de transferencia**
```
DR total: $1.000,00  (del paso 1)
CR total: $950,00 + $50,00 = $1.000,00  (pasos 2 y 3)
Saldo: $0,00 ✓
```

---

## Jerarquía de configuración

Cuando el módulo calcula la comisión, días de acreditación y diario destino, aplica la siguiente prioridad (mayor a menor):

```
Plan de cuotas  →  Tarjeta  →  Procesador
```

Si un plan tiene configurado su propio diario de acreditación, usa ese. Si no, cae al de la tarjeta. Si la tarjeta tampoco tiene, usa el del procesador. El primer valor no nulo gana.

---

## Control de acreditaciones

Opción disponible en la pestaña "Tarjetas PRS" del **banco receptor**.

| Estado | Comportamiento |
|---|---|
| ❌ Desactivado | El cron acredita automáticamente al vencer el plazo configurado en la tarjeta |
| ✅ Activado | El flujo queda en estado `Esperando acreditación`. El cron no lo procesa. Requiere confirmación manual desde el botón "Acreditaciones pendientes" en el diario |

**Cuándo activarlo**: cuando se quiere comparar la liquidación real del procesador (CSV/PDF que envían) contra lo calculado por el sistema antes de impactar en el banco. Permite detectar diferencias de comisión o retenciones antes de confirmar.
