# Padrón Electoral - Control de Voto y Traslado (Odoo 18)

**Módulo:** `padron_control`  
**Versión:** 18.0.1.0.3  
**Licencia:** LGPL-3  
**Categoría:** Operations  
**Dependencias:** `base`, `contacts`, `fleet`

Gestión operativa de un **padrón electoral** en Odoo: carga de personas (Contactos), asignación por **Mesa** y **Vehículo**, **marcación rápida de voto** (modo operador) y **control de traslado** por vehículo, con seguridad por **mesas asignadas al usuario**.

---

## ✅ Funcionalidades principales

### 1) Personas del padrón (Contactos)

Se extiende `res.partner` con campos específicos:

- **Es del Padrón** (`is_padron_person`)
- **DNI** (`dni`)
- **N° de Trámite** (`tramite`)
- **Mesa N°** (`mesa_id`)
- **Vehículo** (`vehicle_id`)
- Estado simple de voto (para operación y contadores):
  - `padron_vote_state`: `not_voted` / `voted`
  - `padron_vote_datetime`
  - `padron_vote_user_id`

Además, cuando un contacto está marcado como padrón, el formulario se “simplifica”:

- se ocultan pestañas (notebook),
- y se ocultan campos típicos de contacto que no aplican (vat, email, website, mobile, company fields, etc.).

---

### 2) Mesas

Modelo `padron.mesa`:

- **Mesa N°** (única)
- **Zona / Circuito**

---

### 3) Eventos / Jornadas

Modelo `padron.event`:

- Nombre
- Fecha
- Estado: `draft` / `active` / `closed`

Reglas:

- Solo puede haber **1 evento activo** a la vez (al activar uno, los demás vuelven a borrador).
- Un evento activo puede **cerrarse**.

---

### 4) Marcación de voto (histórico por evento)

Modelo `padron.checkin` (1 registro por **evento + persona**):

- evento, persona, mesa (relacionada), estado (`voted`, `not_voted`, `absent`, `observed`),
- operador, fecha/hora,
- vehículo (opcional).

> La marcación “rápida” actualiza el estado del contacto y también crea/actualiza el checkin del evento activo.

---

### 5) Control de traslado (histórico por evento)

Modelo `padron.transport.line` (1 registro por **evento + persona**):

- evento, persona, mesa (relacionada)
- vehículo
- estado (`assigned`, `transported`, `no_show`, `reassigned`)
- operador, fecha/hora, nota

---

### 6) Vehículos (Fleet) + asignación de personas

Se extiende `fleet.vehicle` con:

- `padron_person_ids` (personas del padrón asignadas al vehículo)
- contadores:
  - asignados, votaron, faltan/pendientes
  - flag “todos votaron”
- acciones para abrir listas filtradas (asignados / votaron / no votaron)
- wizard para asignación masiva de personas a un vehículo.

---

## 👤 Roles y permisos

El módulo define 3 grupos:

- **Operador Padrón** (`group_padron_operator`)
- **Supervisor Padrón** (`group_padron_supervisor`)
- **Administrador Padrón** (`group_padron_admin`)

### Seguridad por Mesas

En `res.users` se agrega:

- **Mesas asignadas** (`mesa_ids`)

Y se aplican **reglas de registro**:

- Operador/Supervisor: pueden ver/operar **solo personas del padrón de sus mesas** (y sus check-ins / traslados).
- Admin: acceso completo.

Además, hay un control extra en backend (`_padron_assert_user_mesa_access`) que bloquea acciones si el operador intenta operar una persona fuera de sus mesas.

---

## 🧭 Menús y pantallas

### Operador

- **Padrón → Marcar Voto**  
  Wizard modal para buscar por DNI/Trámite y marcar.

### Supervisor / Admin

- **Padrón → Operación → Control de Votantes**  
  Lista con filtros (Votó / No votó), y botones “Marcar Votó / Desmarcar”.
- **Padrón → Operación → Personas (Padrón)**  
  Listado completo del padrón (según permisos).
- **Padrón → Operación → Marcaciones de Voto**  
  Histórico `padron.checkin`.
- **Padrón → Operación → Control de Traslado**  
  Vista simplificada de vehículos con contadores y acceso a personas asignadas.
- **Padrón → Operación → Marcar Traslado (Rápido)**  
  Wizard modal para registrar traslado por DNI/Trámite.
- **Padrón → Configuración → Mesas / Eventos**

---

## ⚡ Flujo operativo recomendado

### Paso 1: Crear Mesas

1. Padrón → Configuración → **Mesas**
2. Crear mesas y/o zonas.

### Paso 2: Cargar el padrón (personas)

Usar **Contactos** (importación estándar de Odoo) y cargar:

- `is_padron_person = True`
- `dni`, `tramite`
- `mesa_id` (Mesa)
- dirección si aplica

> No hay wizard de importación propio: se usa el importador de Contactos.

### Paso 3: Crear y activar un Evento

1. Padrón → Configuración → **Eventos**
2. Crear evento (fecha)
3. Botón **Activar** (deja 1 solo evento activo)

### Paso 4: Asignar Mesas a usuarios

1. Ajustes → Usuarios → abrir usuario
2. Pestaña **Padrón**
3. Asignar `mesa_ids` (visible para Supervisor/Admin)

### Paso 5: Operar el día de la elección

- Operador abre **Marcar Voto** y carga DNI/Trámite → **Marcar Votó**
- El sistema:
  - actualiza el contacto (votó + fecha/hora + usuario)
  - crea/actualiza el `padron.checkin` del evento activo

### Paso 6 (opcional): Traslados por vehículo

- Supervisor/Admin usa:
  - **Control de Traslado** (vehículos y personas asignadas)
  - o **Marcar Traslado (Rápido)** para registrar estado y nota

---

## 🧾 Wizards incluidos

### Marcar Voto (Rápido) — `padron.quick.vote.wizard`

- Busca por DNI o Trámite.
- Normaliza DNI (acepta con o sin puntos y separadores).
- Restringe por mesas del usuario (si tiene asignadas).
- Requiere **evento activo** para registrar el check-in.
- Se resetea automáticamente para el siguiente escaneo/carga.

### Marcar Traslado (Rápido) — `padron.quick.transport.wizard`

- Busca por DNI o Trámite (dentro de mesas asignadas).
- Requiere elegir vehículo y estado.
- Crea/actualiza `padron.transport.line`.

### Asignar personas a vehículo — `padron.vehicle.assign.wizard`

- Selecciona múltiples personas del padrón para asignar a un vehículo.
- Opción **“Reemplazar asignación actual”**: desasigna primero a los ya asignados a ese vehículo.

---

## 🖥️ Modo Kiosk (Operador) — (Opcional)

El módulo incluye JS/SCSS para un “modo kiosco”:

- al iniciar sesión como **Operador**, abre automáticamente el wizard,
- oculta navegación y panel de control,
- evita cerrar el modal con ESC,
- fuerza redirección al wizard si intenta navegar.

⚠️ **Importante:** en esta versión del módulo, esos assets existen en `static/src/` pero **no están declarados en `__manifest__.py`**.  
Si querés activarlo, agregá:

```python
'assets': {
    'web.assets_backend': [
        'padron_control/static/src/js/operator_kiosk.js',
        'padron_control/static/src/scss/operator_kiosk.scss',
    ],
},
```
