# Payment Register → Statement Line (PRS)

**Versión:** 18.0.2.1.0  
**Autor:** Alderete Informática (basado en Mohamed Elkmeshi)  
**Licencia:** LGPL-3  
**Compatibilidad:** Odoo 18  

---

## ¿Qué hace este módulo?

Cuando se valida un pago en un diario de tipo **Banco** o **Caja** con la opción *Crear extractos automáticos* activa, el módulo crea automáticamente una línea en el extracto bancario (bank statement line) sin intervención manual.

Esto elimina el paso de cargar manualmente cada movimiento en la conciliación bancaria y garantiza que cada pago quede trazado en el tablero de conciliación de Odoo.

---

## Módulos complementarios requeridos

El módulo funciona de forma autónoma, pero se integra con:

| Módulo | Función |
|---|---|
| `l10n_ar_multi_payment_withholding` | Multi-pago argentino con cheques y retenciones |
| `l10n_latam_check` | Cheques propios y de terceros (localización AR) |
| `pos_cash_transfer` | Depósitos de caja POS → Caja Central |
| `l10n_ar_withholding` | Retenciones impositivas argentinas |

---

## Instalación

```bash
# Copiar el módulo en la carpeta de addons
cp -r payment_register_statement /path/to/odoo/addons/

# Instalar
./odoo-bin -i payment_register_statement -d nombre_base --stop-after-init

# Para actualizar una versión existente
./odoo-bin -u payment_register_statement -d nombre_base --stop-after-init
```

---

## Configuración por diario

Ir a **Contabilidad → Configuración → Diarios → [seleccionar diario]**, sección **Extractos automáticos**.

| Campo | Default | Descripción |
|---|---|---|
| **Crear extractos automáticos** | `False` | Activa la creación automática de líneas de extracto al validar pagos en este diario. Debe activarse diario por diario. |
| **Calcular aut. saldo estados de cuenta** | `False` | El módulo calcula `balance_start` y `balance_end_real` automáticamente en cadena. Si está desactivado, los saldos se ingresan manualmente. |
| **Solo contabilizar conciliados** | `False` | El balance del diario (panel izquierdo) solo cuenta líneas ya conciliadas. Útil para diarios de tarjetas donde el saldo real se conoce recién cuando el proveedor acredita. |
| **Extracto por cheque individual** | `False` | Cuando un pago tiene múltiples cheques (l10n_latam), crea una línea de extracto por cada cheque usando su número como referencia. Si está desactivado, se crea un único extracto por el total del pago. |
| **Avisar si falta Memo** | `True` | Envía una notificación de advertencia al validar un pago sin campo Memo. Desactivar en diarios POS o automáticos donde el memo no es relevante. |

### Configuración recomendada por tipo de diario

#### Diario Banco (transferencias, débitos)
```
Crear extractos automáticos:  ✅
Calcular aut. saldo:          ✅
Solo contabilizar conciliados: ❌
Extracto por cheque:          según necesidad del cliente
Avisar si falta Memo:         ✅
```

#### Diario Caja (efectivo)
```
Crear extractos automáticos:  ✅
Calcular aut. saldo:          ✅
Solo contabilizar conciliados: ❌
Extracto por cheque:          ❌ (no aplica)
Avisar si falta Memo:         ✅
```

#### Diario Tarjetas de Crédito (POS)
```
Crear extractos automáticos:  ✅
Calcular aut. saldo:          ✅
Solo contabilizar conciliados: ✅  ← clave para mostrar $0 hasta acreditación
Extracto por cheque:          ❌
Avisar si falta Memo:         ❌  ← el POS no usa Memo
```

#### Diario Caja POS (sucursal)
```
Crear extractos automáticos:  ✅
Calcular aut. saldo:          ✅
Solo contabilizar conciliados: ❌
Extracto por cheque:          ❌
Avisar si falta Memo:         ❌  ← el cierre POS no usa Memo
```

---

## Flujos contables

### Flujo 1 — Pago simple (efectivo / transferencia)

Al validar un pago en un diario habilitado:

```
PBNK/BNK (pago)
  Débito  2.1.1.01.010 Proveedores        $X
  Crédito 1.1.1.02.004 Pagos pendientes   $X

BNK (extracto — creado por PRS)
  Crédito 1.1.1.02.005 Banco              $X
  Débito  1.1.1.02.002 Cuenta transitoria $X   ← pendiente de conciliar
```

### Flujo 2 — Pago con múltiples cheques (requiere `prs_split_checks_per_statement = True`)

Con 2 cheques de $15.000:

```
PBNK (pago)
  Crédito 1.1.1.02.004 Pagos pendientes   $30.000
  Débito  2.1.1.01.010 Proveedores        $30.000

BNK extracto cheque 32132136464 — creado por PRS
  Crédito 1.1.1.02.005 Banco              $15.000
  Débito  1.1.1.02.002 Cuenta transitoria $15.000

BNK extracto cheque 654646464 — creado por PRS
  Crédito 1.1.1.02.005 Banco              $15.000
  Débito  1.1.1.02.002 Cuenta transitoria $15.000
```

### Flujo 3 — Transferencia interna (misma empresa)

Desde el botón **Transferencia interna** del tablero bancario:

```
BNK origen (salida)
  Crédito Banco origen                    $X
  Débito  6.0.00.00.01 Transf. liquidez  $X

BNK destino (entrada)
  Débito  Banco destino                   $X
  Crédito 6.0.00.00.01 Transf. liquidez  $X

→ Los apuntes de 6.0.00.00.01 se reconcilian automáticamente
→ Ambas líneas quedan marcadas como "Comprobado" (no "Por revisar")
```

### Flujo 4 — Transferencia interna cross-company (sucursal → central)

Igual al Flujo 3 pero entre empresas distintas. La cuenta de transferencia **no se reconcilia** (Odoo no permite reconciliación entre empresas). El saldo queda abierto en cada empresa como registro del intercompañía.

### Flujo 5 — Cierre POS con efectivo

```
Pago POS (creado por Odoo al cerrar sesión)
  Débito  1.1.1.01.00X Caja sucursal      $X
  Crédito 1.1.3.01.020 Créd. ventas PoS  $X

BNK extracto — creado por PRS
  Débito  Caja sucursal                   $X
  Crédito Cuenta transitoria (suspense)   $X
```

### Flujo 6 — Cierre POS con tarjeta de crédito

PRS **no crea extracto bancario** cuando el pago POS usa un diario cuya cuenta es de tipo *Por Cobrar* (`asset_receivable`). El banco se registra recién cuando el proveedor de tarjetas acredita, mediante una Transferencia Interna.

```
Cierre POS → detecta diario con cuenta Por Cobrar → omite extracto

Cuando el proveedor acredita (Transferencia Interna):
  BNK Tarjetas (salida)
    Crédito 1.1.3.01.016 Tarjetas a cobrar  $X
    Débito  6.0.00.00.01 Transf. liquidez   $X

  BNK Banco (entrada)
    Débito  Banco                            $X
    Crédito 6.0.00.00.01 Transf. liquidez   $X

→ Reconciliación automática de la cuenta de transferencia
```

---

## Transferencia interna cross-company

El wizard de **Transferencia interna** permite mover fondos entre diarios de **distintas empresas** (ej. Caja sucursal BONSI PLAZA → Caja Central SIUBON S.R.L.).

Para que el diario destino aparezca en el selector cuando es de otra empresa, el wizard no filtra por `company_id` — muestra todos los diarios de tipo Banco/Caja a los que el usuario tiene acceso.

---

## Multiempresa — Diarios de caja compartidos

Los diarios de tipo **Caja** pueden habilitarse para múltiples empresas mediante el campo **Empresas permitidas** en la configuración del diario.

Esto permite, por ejemplo, que una empresa sucursal registre pagos en el diario de caja de la empresa central sin que se genere un error de acceso.

---

## Permisos

| Grupo | Permiso |
|---|---|
| `group_prs_assign_payments_to_statements` | Permite asignar manualmente un pago a un Estado de Cuenta específico desde el formulario del pago. |

---

## Estructura del módulo

```
payment_register_statement/
├── models/
│   ├── prs_utils.py                    # Funciones shared: prs_is_pos, prs_journal_uses_receivable
│   ├── account_payment.py              # Lógica principal de extractos automáticos
│   ├── account_journal.py              # Campos de configuración del diario
│   ├── account_bank_statement.py       # Estados de cuenta: ciclo de vida, saldos encadenados
│   ├── account_bank_statement_line.py  # Líneas de extracto: herencia de partner y concepto
│   ├── account_move.py                 # Validación multiempresa en asientos manuales
│   ├── internal_transfer_wizard.py     # Wizard de transferencia interna (con soporte cross-company)
│   ├── expense_concept.py              # Modelo prs.expense.concept
│   ├── misc_expense.py                 # Gastos varios
│   └── res_partner.py                  # Campo concepto de gasto en contacto
├── views/
│   ├── account_journal_view.xml        # Sección "Extractos automáticos" en el diario
│   ├── internal_transfer_wizard_view.xml
│   └── ...
├── security/
│   ├── prs_groups.xml
│   └── ir.model.access.csv
└── static/src/
    ├── cog_menu/                       # Botón Transferencia interna en tablero bancario
    ├── bank_rec_button/                # Integración con widget de conciliación
    └── live_refresh/                   # Refresco en tiempo real del balance
```

---

## API — Métodos sobreescribibles

Todos los métodos de `AccountPayment` relacionados con la creación de extractos pueden sobreescribirse desde módulos dependientes sin tocar este módulo.

| Método | Cuándo sobreescribir |
|---|---|
| `_prs_get_payment_label()` | Cambiar el formato de la etiqueta del extracto |
| `_prs_should_skip_pos_receivable(journal)` | Cambiar la lógica de detección de tarjetas POS |
| `_prs_get_statement_for_payment(journal)` | Cambiar cómo se elige el Estado de Cuenta |
| `_prs_get_last_statement_for_journal(journal)` | Cambiar el criterio de búsqueda del último estado |
| `_prs_get_check_lines(sign)` | Cambiar cómo se desglosan los cheques |
| `_prs_build_base_statement_vals(...)` | Agregar campos custom al extracto |
| `_prs_create_statement_lines()` | Reemplazar toda la lógica de creación |
| `_prs_warn_missing_memo()` | Cambiar el comportamiento de la advertencia |
| `_prs_assign_pos_partner()` | Cambiar cómo se asigna el partner POS |

**Ejemplo — agregar un campo custom al extracto desde otro módulo:**

```python
class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _prs_build_base_statement_vals(self, journal, statement, label, amount_signed):
        vals = super()._prs_build_base_statement_vals(journal, statement, label, amount_signed)
        vals['x_mi_campo_custom'] = self.x_mi_campo_custom
        return vals
```

---

## Historial de versiones

| Versión | Cambios principales |
|---|---|
| `18.0.2.1.0` | Refactorización: `action_post` dividido en métodos sobreescribibles. Nuevos flags `prs_split_checks_per_statement` y `prs_warn_missing_memo`. `AccountMove` movido a `account_move.py`. Label `[GV]` centralizado en `_prs_get_payment_label()`. |
| `18.0.2.0.1` | Soporte transferencias cross-company. Reconciliación automática en transferencia interna (sin "Por revisar"). |
| `18.0.1.2.1` | Balance "solo conciliados" separado del `running_balance` nativo de Odoo. |
| `18.0.1.0.7` | Eliminación de Smart Reconcile. Soporte flujo tarjetas POS (skip extracto en cuenta Por Cobrar). |
| `18.0.1.0.0` | Versión inicial: extractos automáticos al validar pagos en diarios de caja/banco. |

---

## Problemas conocidos

**Columnas huérfanas en BD:** al eliminar el smart reconcile en v1.0.7, los campos `prs_smart_reconcile_models`, `prs_smart_reconcile_auto` y `prs_pos_receivable` quedaron como columnas en la base de datos. Son inofensivas pero pueden limpiarse manualmente:

```sql
ALTER TABLE account_journal DROP COLUMN IF EXISTS prs_smart_reconcile_models;
ALTER TABLE account_journal DROP COLUMN IF EXISTS prs_smart_reconcile_auto;
ALTER TABLE account_bank_statement_line DROP COLUMN IF EXISTS prs_pos_receivable;
```

**Vista del diario en BD:** si al actualizar el módulo aparece el error `prs_smart_reconcile_models field is undefined`, la vista XML del diario tiene el arch viejo en la base de datos. Solucionarlo desde **Ajustes → Técnico → Vistas**, buscar `account.journal.form.auto.extract.multi.company` y borrar el grupo "Conciliación Smart" del arch, luego actualizar con `-u`.
