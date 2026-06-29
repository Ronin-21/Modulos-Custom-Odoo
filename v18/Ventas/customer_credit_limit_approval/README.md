# Límite de Crédito del Cliente con Aprobación

**Versión:** 18.0.1.0  
**Odoo:** 18  
**Licencia:** LGPL-3  
**Autor:** Abel Alejandro Acuña — Alderete Informática  
**Dependencias:** `sale_management`

> Para integración con el Punto de Venta instalar el módulo complementario `customer_credit_limit_approval_pos`.

---

## Descripción

Agrega un control de **límite de crédito por cliente** sobre las Órdenes de Venta. Cuando una venta supera el límite configurado, el sistema bloquea la confirmación y dispara un flujo de aprobación con notificaciones para los aprobadores y el vendedor.

---

## Funcionalidades

### 1. Configuración de límites en el contacto

En la pestaña **"Cuenta corriente"** del contacto se configuran:

| Campo | Descripción |
|-------|-------------|
| **Crédito activo** | Activa/desactiva el control de crédito para este cliente. Si está desactivado, el módulo no interviene. |
| **Monto de advertencia** | Referencia visual. No bloquea la operación al superarlo. |
| **Monto de bloqueo** | Límite real. Al superarlo (deuda total + operación), la confirmación queda bloqueada hasta aprobación. |

La misma pestaña muestra el **estado de cuenta** en tiempo real:

| Campo | Qué incluye |
|-------|-------------|
| **Deuda facturada (contable)** | `débito - crédito` de los movimientos contables del partner |
| **Ventas confirmadas sin facturar** | Órdenes de venta en estado *Venta* que aún no fueron totalmente facturadas |
| **Deuda Total** | Suma de los componentes anteriores. Este es el valor que se compara contra el límite. |

> La **Deuda Total** se recalcula automáticamente cuando cambia el estado de una SO o sus facturas.

---

### 2. Validación al confirmar una Orden de Venta

Al presionar **Confirmar**:

1. El sistema calcula: `Deuda Total del cliente + Total de la orden`.
2. Si ese resultado **supera el monto de bloqueo** y el crédito no fue previamente aprobado, se abre un wizard que muestra el exceso e invita al vendedor a enviar la orden para aprobación.
3. Si no supera el límite, la orden se confirma normalmente.

---

### 3. Estados adicionales en la Orden de Venta

| Estado | Etiqueta | Descripción |
|--------|----------|-------------|
| `sales_approval` | Aprobación de Crédito | La orden espera revisión. No se puede confirmar. |
| `approved` | Aprobado | El aprobador autorizó el crédito. El vendedor puede confirmar. |
| `reject` | Rechazado | La operación fue rechazada. Requiere intervención manual. |

#### Flujo completo

```
Borrador / Enviada
      │
      │  [Confirmar → excede límite]
      ▼
 Wizard: "Enviar para Aprobación"
      │
      │  [Vendedor confirma envío]
      ▼
Aprobación de Crédito  ──[Rechazar]──►  Rechazado
      │                                      │
      │  [Aprobar]                           │  [Volver a Borrador]
      ▼                                      ▼
  Aprobado                               Borrador
      │
      │  [Confirmar]
      ▼
  Venta (confirmada)
```

---

### 4. Notificaciones y actividades

#### Al enviar a aprobación (vendedor)
- Nota interna en el chatter con el detalle del exceso.
- Suscripción automática de todos los aprobadores al hilo.
- Actividad "Revisar aprobación de crédito" creada para cada aprobador (sin duplicados).

#### Al aprobar
- Nota interna confirmando la aprobación.
- Actividad creada para el vendedor: *"Orden aprobada: confirmar venta"*.

#### Al rechazar
- Nota interna indicando el rechazo.
- Actividad creada para el vendedor: *"Orden rechazada por crédito"*.

> Todas las notificaciones se postean en modo **silencioso** (sin envío de correo) para evitar errores en entornos sin SMTP configurado.

---

## Configuración

### Paso 1 — Activar el crédito en los clientes

1. Ir al contacto del cliente → pestaña **Cuenta corriente**.
2. Marcar **Crédito activo**.
3. Completar el **Monto de bloqueo** (valor a partir del cual se bloquea la operación).
4. Opcionalmente, completar el **Monto de advertencia** (solo referencia visual).

### Paso 2 — Asignar permisos de aprobación

Los usuarios que deban **aprobar, rechazar o volver a borrador** órdenes de crédito deben tener habilitado el permiso:

> **Ventas → Aprobador de Límite de Crédito**

Se asigna desde **Ajustes → Usuarios → [usuario] → Derechos de acceso → sección Ventas**.

---

## Permisos

| Acción | Permiso requerido |
|--------|------------------|
| Confirmar una SO | Vendedor asignado, o Gerente de Ventas / ERP Manager |
| Enviar a aprobación de crédito | Vendedor asignado a la orden |
| Aprobar crédito | **Aprobador de Límite de Crédito** |
| Rechazar crédito | **Aprobador de Límite de Crédito** |
| Volver a borrador | **Aprobador de Límite de Crédito** |

> Un vendedor no puede enviar ni confirmar órdenes de otro vendedor, salvo que sea Gerente de Ventas o ERP Manager.

---

## Notas técnicas

- La **Deuda Total** (`amount_due`) es un campo `store=False` — no existe en la base de datos. No usar en filtros SQL directos ni en `search()` sobre el campo en sí.
- El permiso de aprobación es independiente del rol de administrador: un usuario puede ser ERP Manager sin poder aprobar crédito, y viceversa.
