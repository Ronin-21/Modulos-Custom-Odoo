# payment_register_statement_ar_v19

Módulo de integración para Argentina. Corrige el seguimiento de estado de cheques de terceros en Odoo 19, reemplazando el filtro nativo roto con estados calculados correctamente según el recorrido real del cheque.

**Depende de:** `payment_register_statement_v19`, `l10n_latam_check`

---

## Problema que resuelve

El módulo nativo `l10n_latam_check` incluye un filtro "A la mano" (`checks_on_hand`) basado en el campo `issue_state`, que solo se calcula correctamente para **cheques propios**. Para cheques de terceros ese campo nunca refleja el estado real, por lo que el filtro no funciona.

Este módulo reemplaza ese mecanismo con un campo computado propio que deriva el estado del cheque a partir de su **historial de operaciones** y el **diario donde se encuentra actualmente**.

---

## Estados agregados

El campo `prs_third_party_state` puede tomar cuatro valores:

| Estado | Etiqueta | Badge | Significado |
|---|---|---|---|
| `holding` | En cartera | Verde | El cheque está en un diario marcado como "Diario de cheques de terceros" |
| `cashed` | Cobrado en efectivo | Azul oscuro | Transferido a un diario de caja **sin** ese flag — cobrado en ventanilla |
| `deposited` | Depositado | Azul | El cheque fue depositado en un diario de tipo Banco |
| `endorsed` | Endosado / Entregado | Naranja | El cheque salió del sistema hacia un tercero (no a un banco) |

### Lógica de cálculo

```
¿Tiene current_journal_id?
  ├─ Sí, tipo banco                          → deposited
  ├─ Sí, tipo caja + prs_check_journal=True  → holding
  ├─ Sí, tipo caja + prs_check_journal=False → cashed
  └─ No (salió de todos los diarios)
       ├─ Última operación saliente → banco   → deposited
       └─ Última operación saliente → tercero → endorsed
```

### Configuración requerida: marcar el diario de cheques

El campo `prs_check_journal` distingue los diarios de cartera de cheques de los diarios de efectivo. **Sin esta configuración, todos los cheques en caja aparecerán como "Cobrado en efectivo".**

Ir a **Contabilidad → Configuración → Diarios → [Cheques de Terceros] → Configuración avanzada → Cheques de Terceros (PRS)** y activar **"Diario de cheques de terceros"**.

Hacer esto en cada diario que actúe como cartera de cheques (usualmente uno por empresa/sucursal).

### Campo adicional: `prs_endorsed_to_id`

Cuando el estado es `endorsed`, este campo indica el **contacto** al que se le entregó o endosó el cheque. Se calcula a partir del último pago saliente validado en el historial de operaciones del cheque.

---

## Cambios en la vista

### Lista de cheques de terceros

- Agrega la columna **Estado** con badge de color:
  - Verde → En cartera
  - Naranja → Entregado/Endosado
  - Azul → Depositado
- Agrega la columna **Entregado a** (opcional, visible bajo demanda)

### Filtros de búsqueda

Reemplaza el filtro nativo "A la mano" por tres filtros separados:

| Filtro | Dominio |
|---|---|
| En cartera | `prs_third_party_state = 'holding'` |
| Entregado / Endosado | `prs_third_party_state = 'endorsed'` |
| Depositado | `prs_third_party_state = 'deposited'` |

Agrega también:
- Campo de búsqueda por **Entregado a** (contacto destinatario)
- Agrupadores por **Estado** y por **Entregado a**

### Vista por defecto

Al abrir "Cheques de terceros", el filtro **En cartera** está activo por defecto (equivalente al comportamiento esperado del filtro nativo).

---

## Sin configuración adicional

El módulo no agrega campos en Ajustes ni requiere configuración. Se activa automáticamente al instalarse, siempre que `l10n_latam_check` esté instalado.
