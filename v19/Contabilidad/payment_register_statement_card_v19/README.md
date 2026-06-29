# PRS Tarjetas y Cash Flow

**Versión:** 19.0.1.0.0  
**Licencia:** LGPL-3  
**Compatibilidad:** Odoo 19  
**Depende de:** `payment_register_statement_v19`

---

## ¿Qué hace este módulo?

Extiende el módulo base de PRS para agregar soporte completo de cobros con tarjeta de crédito y débito:

- Modelos de tarjeta (`account.card`) y plan de cuotas (`account.card.installment`) con comisiones, retenciones y días de acreditación.
- Procesadores de tarjetas (`prs.card.provider`) como agrupador de tarjetas por proveedor (Payway, Clover, Mercado Pago, etc.).
- Selección de tarjeta y plan al registrar un pago.
- Generación automática de `prs.money.flow` de tipo `card_settlement` con fecha de acreditación calculada.
- Acreditación contable completa: transferencia interna diario puente → banco receptor con registro de comisión.
- Control manual de acreditaciones por diario (confirmación humana antes de impactar el banco).
- Tarjetas globales (sin empresa) disponibles en todas las sucursales.
- Wizard para asignar tarjetas sueltas a un procesador.

---

## Índice

1. [Instalación](#instalación)
2. [Conceptos clave](#conceptos-clave)
3. [Configuración global (Ajustes)](#configuración-global-ajustes)
4. [Tarjetas precargadas](#tarjetas-precargadas)
5. [Procesadores de tarjetas](#procesadores-de-tarjetas)
6. [Tarjetas](#tarjetas)
7. [Planes de cuotas](#planes-de-cuotas)
8. [Jerarquía de configuración](#jerarquía-de-configuración)
9. [Configuración del diario puente](#configuración-del-diario-puente)
10. [Configuración del banco receptor](#configuración-del-banco-receptor)
11. [Cuentas contables recomendadas](#cuentas-contables-recomendadas)
12. [Flujo contable completo](#flujo-contable-completo)
13. [Control de acreditaciones](#control-de-acreditaciones)
14. [Flujo de Pagos — card_settlement](#flujo-de-pagos--card_settlement)
15. [Métodos de pago internos](#métodos-de-pago-internos)
16. [Tarjetas globales (sin empresa)](#tarjetas-globales-sin-empresa)
17. [Estructura del módulo](#estructura-del-módulo)

---

## Instalación

```bash
./odoo-bin -i payment_register_statement_card_v19 -d nombre_base --stop-after-init
```

Al instalar se crean 7 tarjetas precargadas sin empresa ni procesador (ver [Tarjetas precargadas](#tarjetas-precargadas)).

---

## Conceptos clave

El módulo opera con dos diarios separados y una cuenta de tránsito:

| Elemento | Rol | Ejemplo |
|---|---|---|
| **Diario puente** | Recibe el bruto al momento de la venta | Tarjetas Clover |
| **Banco receptor** | Recibe el neto que deposita el procesador | Banco Santander |
| **Cuenta de transferencia** | Puente contable entre ambos | `6.0.00.00.01 Transferencias internas` |

La cuenta de transferencia arranca en $0 y termina en $0 al finalizar cada acreditación. El sistema la encuentra automáticamente desde `Ajustes → Contabilidad → Transferencia de liquidez` o buscando una cuenta con ese nombre.

---

## Configuración global (Ajustes)

`Ajustes → Contabilidad → Cobros con Tarjeta`

Permite configurar las **cuentas contables predeterminadas** para comisiones, IVA y retenciones a nivel de empresa. Estas aplican a todos los diarios puente que no tengan cuentas propias.

| Campo | Tipo de cuenta | Descripción |
|---|---|---|
| Cuenta comisiones predeterminada | `expense` | Gasto por comisiones del procesador |
| Cuenta IVA comisión predeterminada | `asset_current` o `expense` | IVA sobre la comisión |
| Cuenta retenciones predeterminada | `asset_current` o `liability_current` | Retenciones/percepciones sufridas |

Estas cuentas pueden sobreescribirse por diario en la pestaña **Tarjetas PRS** de cada journal.

---

## Tarjetas precargadas

Al instalar el módulo se crean 7 tarjetas globales con `noupdate="1"`:

| ID XML | Nombre |
|---|---|
| `card_visa_credit` | Visa Crédito |
| `card_visa_debit` | Visa Débito |
| `card_amex` | AMEX |
| `card_master_credit` | Mastercard Crédito |
| `card_master_debit` | Mastercard Débito |
| `card_naranja` | Naranja |
| `card_maestro` | Maestro |

Estas tarjetas no tienen empresa ni procesador asignado. Sirven como punto de partida: se les puede asignar un procesador desde el formulario del procesador (botón "Asignar tarjeta existente") o configurando directamente la tarjeta.

El flag `noupdate="1"` garantiza que las modificaciones hechas en la base de datos no se sobreescriban al actualizar el módulo.

---

## Procesadores de tarjetas

`Configuración → Cobros con Tarjeta → Procesadores`

Modelo `prs.card.provider`. Agrupa las tarjetas de un mismo proveedor y define los valores por defecto que heredan sus tarjetas.

| Campo | Descripción |
|---|---|
| Nombre | Ej: CLOVER, Payway, Mercado Pago |
| Contacto | Proveedor del procesador en la master de contactos. Se usa como partner en la línea de extracto del banco receptor y en el asiento de comisión |
| Código | Identificador técnico para integraciones (ej: `clover`) |
| Empresa | Obligatorio — el procesador es siempre por empresa |
| Diario de acreditación | Banco receptor donde deposita este procesador |
| Días de acreditación | Plazo estándar (0 = mismo día) |
| Tipo de días | Corridos o hábiles |
| Comisión (%) | Porcentaje de comisión base |
| Comisión fija | Monto fijo adicional a la comisión porcentual |
| IVA comisión (%) | Porcentaje de IVA sobre la comisión |
| Retención (%) | Porcentaje de retención/percepción aplicada |

### Partner del procesador en el flujo contable

Cuando el procesador tiene un `Contacto` asignado, ese partner se propaga automáticamente durante la acreditación a:

- **Línea de extracto del banco receptor** (`dst_line`): la línea que registra la entrada del neto acreditado muestra el procesador como partner, facilitando la búsqueda y los reportes por procesador en el tablero bancario.
- **Asiento de comisión**: tanto el encabezado del asiento como la línea de gasto (DR comisiones) quedan vinculados al procesador, permitiendo AP aging y seguimiento de comisiones por proveedor.

> La línea de extracto del diario puente (`src_line`) conserva el partner del cliente original, ya que es contra ese partner que reconcilia el PBNK.

### Asignar tarjetas existentes

El botón **"Asignar tarjeta existente"** abre un wizard (`prs.card.assign.wizard`) que muestra todas las tarjetas sin procesador. Permite seleccionar múltiples y asignarlas al procesador actual en un solo paso. Esto resuelve el límite del One2many nativo donde "Agregar una línea" solo crea registros nuevos.

---

## Tarjetas

`Configuración → Cobros con Tarjeta → Tarjetas`

Modelo `account.card`. Puede sobreescribir cualquier valor heredado del procesador.

| Campo | Descripción |
|---|---|
| Nombre | Ej: Visa Crédito |
| Empresa | Vacío = tarjeta global disponible en todas las empresas |
| Proveedor | Procesador al que pertenece |
| Método de pago | Vinculación con el `payment.method` nativo de Odoo |
| Número de comercio | Identificador del comercio ante el procesador |
| Días de acreditación | Sobreescribe el del procesador si está definido |
| Tipo de días | Corridos o hábiles |
| Diario de acreditación | Banco receptor específico para esta tarjeta |
| Comisión (%) | Sobreescribe la del procesador |
| Comisión fija | Ídem |
| IVA comisión (%) | Ídem |
| Retención (%) | Ídem |

---

## Planes de cuotas

Pestaña **"Planes"** dentro de la tarjeta. Modelo `account.card.installment`.

| Campo | Descripción |
|---|---|
| Nombre del plan | Ej: "3 cuotas sin interés", "12 cuotas Ahora 12" |
| Plan gateway | ID del plan a informar al gateway de pago electrónico |
| Divisor | Cantidad de cuotas |
| Coeficiente de recargo | Factor sobre el total (1.06 = 6% de recargo). Default 1.0 |
| Descuento del banco | % de reintegro acordado con el banco/marca |
| Aplicar recargo comisiones | Si está activo, se traslada al cliente el cálculo de comisión/IVA/retenciones |
| Días de acreditación | Sobreescribe el de la tarjeta |
| Diario de acreditación | Sobreescribe el de la tarjeta |
| Comisión (%), IVA, Retención | Sobreescriben los de la tarjeta |

El `display_name` del plan es `Nombre (Tarjeta)`, ej: `3 cuotas sin interés (Visa Crédito)`.

---

## Jerarquía de configuración

Al calcular comisiones, días de acreditación y diario destino, el módulo aplica la siguiente prioridad (el primer valor no nulo gana):

```
Plan de cuotas  →  Tarjeta  →  Procesador
```

Ejemplo: si el plan "Ahora 12" tiene su propio diario de acreditación configurado, lo usa. Si no, cae al de la tarjeta. Si la tarjeta tampoco tiene, usa el del procesador.

Este fallback está implementado en `_prs_as_config_dict()` de cada modelo y es el punto de entrada que usa el código de acreditación.

---

## Configuración del diario puente

Este diario recibe el bruto al momento de registrar el pago. El dinero sale cuando se ejecuta la acreditación.

### Pestaña "Asientos contables"

| Campo | Valor recomendado |
|---|---|
| Tipo | Banco |
| Cuenta | Cuenta puente exclusiva para tarjetas (ej. `1.1.1.02.010 Tarjetas a acreditar`) |

La cuenta aquí configurada es la que el sistema busca para reconciliar el pago original con la línea de acreditación. Debe ser la misma que en "Pagos entrantes".

### Pestaña "Pagos entrantes"

| Campo | Valor |
|---|---|
| Cuentas de recibos pendientes | **La misma cuenta** que en "Asientos contables" |

> Esto es obligatorio. Si difieren, el PBNK usa una cuenta distinta y la reconciliación durante la acreditación fallará silenciosamente.

### Pestaña "Tarjetas PRS"

| Campo | Valor |
|---|---|
| Procesador de tarjetas | El procesador correspondiente (ej. CLOVER) |
| Control de acreditaciones | ❌ — el control se configura en el banco receptor |
| Cuenta comisiones / IVA / retenciones | Opcional — si vacío usa las cuentas predeterminadas de la empresa |

### Campos que NO deben activarse en el diario puente

| Campo | Motivo |
|---|---|
| Crear extractos automáticos (`auto_extract_enabled`) | La acreditación crea su propio extracto; este flag generaría un BNK duplicado que rompe la reconciliación |

---

## Configuración del banco receptor

Diario bancario donde el procesador deposita el neto.

### Pestaña "Tarjetas PRS"

| Campo | Descripción |
|---|---|
| Control de acreditaciones | Ver [Control de acreditaciones](#control-de-acreditaciones) |
| Cuenta comisiones | Sobreescribe la predeterminada de la empresa para este banco |
| Cuenta IVA comisión | Ídem |
| Cuenta retenciones | Ídem |

El banco receptor **no necesita** configuración especial en "Pagos entrantes/salientes". La acreditación crea un extracto bancario directamente, no un pago, por lo que la cuenta de recibos pendientes no interviene en este flujo.

---

## Cuentas contables recomendadas

### Cuenta puente de tarjetas

- **Tipo**: Activo corriente (`asset_current`)
- **Reconciliable**: Sí (obligatorio)
- **Ejemplo**: `1.1.1.02.010 Tarjetas a acreditar`
- Acumula el bruto de las ventas con tarjeta hasta la acreditación. Se reconcilia contra $0 al completar el proceso.

### Cuenta de transferencia (liquidez interna)

- **Tipo**: Activo corriente (`asset_current`)
- **Reconciliable**: Sí (obligatorio)
- **Ejemplo**: `6.0.00.00.01 Transferencias internas`
- Configurar en `Ajustes → Contabilidad → Transferencia de liquidez`. Odoo la usa también para transferencias internas entre diarios.
- Su saldo debe ser siempre $0 al finalizar cada acreditación.

### Cuenta de comisiones

- **Tipo**: Gasto (`expense`)
- **Ejemplo**: `5.6.1.01.081 Comisiones bancarias por tarjetas`
- Se debita en cada acreditación por el importe de la comisión del procesador.

### Cuenta de IVA sobre comisiones

- **Tipo**: Activo corriente (`asset_current`) o Gasto (`expense`)
- **Ejemplo Argentina**: `1.1.4.04.010 IVA crédito fiscal — servicios financieros`
- Si el IVA es crédito fiscal recuperable → activo corriente. Si no es recuperable → gasto.

### Cuenta de retenciones / percepciones

- **Tipo**: Activo corriente (`asset_current`) o Pasivo corriente (`liability_current`)
- **Ejemplo Argentina**: `1.1.4.04.030 Retenciones y percepciones a recuperar`
- Las retenciones que el procesador practica sobre la liquidación suelen ser activos a recuperar contra IIBB o Ganancias.

---

## Flujo contable completo

### 1. Al registrar el pago (venta con tarjeta)

```
PBNK — Asiento del pago
  DR  1.1.1.02.010  Tarjetas a acreditar        $1.000,00
      CR  1.1.3.01.001  Cuentas por cobrar           $1.000,00
```

Simultáneamente se crea un `prs.money.flow` de tipo `card_settlement` con la fecha de acreditación calculada según días y tipo de días de la configuración.

### 2. Al ejecutar la acreditación

**Paso 1 — Extracto en el diario puente (bruto sale)**
```
BNK puente — src_line
  DR  6.0.00.00.01  Transferencias internas     $1.000,00
      CR  1.1.1.02.010  Tarjetas a acreditar         $1.000,00
→ Reconcilia con el PBNK original → cuenta puente queda en $0
```

**Paso 2 — Extracto en el banco receptor (neto entra)**
```
BNK receptor — dst_line
  DR  1.1.1.01.002  Banco Santander cta. cte.   $  950,00
      CR  6.0.00.00.01  Transferencias internas      $  950,00
```

**Paso 3 — Asiento de comisión**
```
Asiento comisión
  DR  5.6.1.01.081  Comisiones bancarias        $   42,00
  DR  1.1.4.04.010  IVA crédito fiscal          $    8,00
      CR  6.0.00.00.01  Transferencias internas      $   50,00
```

**Resultado cuenta de transferencia**
```
DR total:  $1.000,00   (paso 1)
CR total:  $  950,00 + $50,00 = $1.000,00   (pasos 2 y 3)
Saldo:     $      0,00  ✓
```

### Extracto legacy (diario puente con auto_extract_enabled activo por error)

Si el diario puente tenía `auto_extract_enabled=True` antes de que esta configuración fuera corregida, puede existir un extracto BNK "legacy" del pago. Durante la acreditación el módulo intenta cancelarlo y eliminarlo automáticamente. Si no es posible, hace un fallback reconciliando sus líneas contra `src_line`.

---

## Control de acreditaciones

Opción en la pestaña **"Tarjetas PRS"** del **banco receptor**.

| Estado | Comportamiento |
|---|---|
| ❌ Desactivado | El cron acredita automáticamente al vencer el plazo |
| ✅ Activado | El flujo queda en `Esperando acreditación`. El cron no lo toca. Requiere confirmación manual |

**Cuándo activarlo**: cuando se quiere comparar la liquidación real del procesador (archivo CSV/PDF) contra lo calculado por el sistema antes de impactar el banco. Permite detectar diferencias de comisión antes de confirmar.

### Wizard de confirmación

Al activar el control, aparece un botón con contador **"Acreditaciones pendientes"** en el formulario del diario. Abre el wizard `prs.accreditation.confirm.wizard` que muestra:

- Lista de flujos pendientes con monto bruto y neto
- Totales consolidados
- Botón **"Confirmar seleccionados"** y **"Confirmar todos"**

El wizard ejecuta `action_create_statement_line()` en los flujos seleccionados, que llama a `_prs_accredit_card_transfer()`.

### Interacción con extractos automáticos del base

Cuando `prs_accreditation_control = True` en el banco receptor:
- `auto_create_statement = False` para ese diario (gestionado automáticamente por el `_inverse`).
- El cron del módulo base omite los flujos con `auto_create_statement=False`.

---

## Flujo de Pagos — card_settlement

El módulo extiende `prs.money.flow` con el tipo `card_settlement` y los campos:

| Campo | Descripción |
|---|---|
| `commission_move_id` | Asiento de comisión creado durante la acreditación |
| `commission_move_count` | Computed: 1 si hay asiento, 0 si no |

El smart button **"Comisión"** en el formulario del flujo navega directamente al asiento de comisión.

### Estados del flujo card_settlement

| Estado | Descripción |
|---|---|
| `waiting_accreditation` | Pendiente (control manual activo) |
| `due` | Plazo vencido pero aún no procesado |
| `statement_created` | Acreditado — extracto creado en el banco receptor |
| `reconciled` | Conciliado contra el saldo real |

### Filtros en la lista de Flujos de Pagos

El módulo agrega dos filtros en la búsqueda de `prs.money.flow`:
- **Liquidaciones de tarjeta** → `flow_type = 'card_settlement'`
- **Pagos directos** → `flow_type != 'card_settlement'`

---

## Métodos de pago internos

El módulo extiende `payment.method` (el modelo nativo de Odoo) con dos modelos auxiliares:

### `prs.payment.method.internal.config`

Configuración interna por empresa y marca/método. Permite que el mismo método de pago Odoo tenga comisiones y diarios de acreditación distintos en cada empresa.

| Campo | Descripción |
|---|---|
| Marca / Método | Referencia al `payment.method` (debe ser una marca, no el método primario) |
| Empresa | Empresa para la que aplica esta configuración |
| Número de comercio | Identificador ante el procesador |
| Días / Tipo de días | Plazo de acreditación |
| Diario de acreditación | Banco receptor para este método en esta empresa |
| Comisión, IVA, Retención | Porcentajes y monto fijo |

Restricción: un solo registro por combinación marca + empresa.

### `prs.payment.method.brand.plan`

Planes de cuotas nativos de Odoo, para integración con POS u otras interfaces que usen `payment.method` directamente en lugar de `account.card`.

| Campo | Descripción |
|---|---|
| Plan | Nombre del plan |
| Marca/Método | `payment.method` de tipo marca |
| Cuotas | Cantidad |
| Recargo del plan (%) | Porcentaje de recargo financiero |
| Aplicar recargo comisiones | Si se traslada el cálculo de comisión al cliente en POS |
| Días / Diario / Comisión | Igual que en `account.card.installment` |

---

## Tarjetas globales (sin empresa)

Una tarjeta con `company_id = False` es **global**: aparece disponible en todas las empresas, independientemente de a cuál esté logueado el usuario.

### Identificación visual

Las tarjetas globales muestran un **ribbon celeste "Global"** en el formulario. Las tarjetas archivadas muestran un ribbon rojo "Archivado".

En la lista, la columna Empresa muestra las filas de tarjetas globales en azul (`decoration-info="not company_id"`).

### Reglas de acceso

Las reglas de registros permiten ver tanto tarjetas propias de la empresa como tarjetas globales:
```python
['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]
```

Lo mismo aplica para los planes de cuotas (`account.card.installment`), que hereda la empresa de su tarjeta padre.

### Consideración al crear planes

Si una tarjeta global tiene un plan de cuotas, ese plan también es visible en todas las empresas. La configuración de diario y cuentas del plan debe ser válida para la empresa donde se use.

---

## Estructura del módulo

```
payment_register_statement_card_v19/
├── models/
│   ├── account_card.py                  # account.card + account.card.installment
│   ├── account_journal_card.py          # Campos del diario puente: procesador, cuentas de comisión
│   ├── account_journal_accreditation.py # prs_accreditation_control: control manual de acreditaciones
│   ├── account_payment_card.py          # Selección de tarjeta en el pago, generación del money flow
│   ├── account_payment_register_card.py # Wizard de registro de pago: extensión para tarjeta
│   ├── payment_method_internal.py       # prs.payment.method.internal.config + brand.plan
│   ├── prs_card_assign_wizard.py        # Wizard para asignar tarjetas sueltas a un procesador
│   ├── prs_card_provider.py             # prs.card.provider
│   ├── prs_money_flow_card.py           # Extensión prs.money.flow: commission_move_id + acreditación
│   └── res_company_card.py              # Cuentas predeterminadas en res.company + res.config.settings
├── wizard/
│   └── prs_accreditation_confirm_wizard.py  # Wizard de confirmación de acreditaciones pendientes
├── views/
│   ├── account_card_prs_views.xml           # Vistas de account.card (lista, form, search)
│   ├── account_journal_card_views.xml       # Pestaña "Tarjetas PRS" en el diario
│   ├── account_payment_card_views.xml       # Campos tarjeta y plan en el formulario de pago
│   ├── account_payment_register_card_views.xml
│   ├── payment_method_internal_views.xml
│   ├── prs_accreditation_confirm_wizard_views.xml
│   ├── prs_card_assign_wizard_views.xml
│   ├── prs_card_provider_views.xml
│   ├── prs_money_flow_card_views.xml        # Filtros y smart button comisión
│   └── res_config_settings_card_views.xml   # Sección en Ajustes
├── data/
│   ├── account_card.xml                 # 7 tarjetas precargadas (noupdate=1)
│   └── decimal_installment_coefficient.xml  # Precisión decimal para coeficiente de cuotas
├── security/
│   ├── account_card_rules.xml           # Reglas: tarjeta global o de la empresa actual
│   └── ir.model.access.csv
├── static/src/
│   └── bank_rec_button/                 # Botón JS de acreditación en el widget de conciliación
└── doc/
    └── config.md                        # Guía de configuración (referencia rápida)
```

---

## Historial de versiones

| Versión | Cambios principales |
|---|---|
| `19.0.1.0.0` | Versión inicial Odoo 19. Extracción desde `payment_register_statement_v19`. Tarjetas globales (sin empresa). Wizard asignación tarjetas. Smart button comisión. Filtros card_settlement / pagos directos. Lógica de extracto legacy. |
