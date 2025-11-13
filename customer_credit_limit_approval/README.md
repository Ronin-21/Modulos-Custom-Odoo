# 🏦 Aprobación de Límite de Crédito en Ventas

**Versión:** 1.0  
**Probado en:** Odoo 18  
**Dependencias:** `sale_management` (usa chatter y actividades de `mail`)

---

## 📋 Descripción

Este módulo agrega un control de **límite de crédito por cliente** sobre las órdenes de venta.  
Cuando una venta supera el límite configurado en el cliente, la orden no se confirma de inmediato sino que pasa a un estado de **aprobación de crédito**, donde un usuario con permisos (ERP manager / ventas admin) puede aprobar o rechazar.

El módulo también crea **actividades (campanita)** para avisar a los gerentes que hay una cotización para revisar, y otra actividad para el vendedor cuando la gerencia aprueba o rechaza.

---

## 🎯 Objetivo

Evitar que se confirmen ventas de clientes que superaron su límite de crédito sin que antes alguien de administración/gerencia lo vea y lo autorice.

---

## ✨ Funcionalidades

### 1. Control por cliente

En el contacto se usan los campos de crédito del partner:

- **credit_check**: activa/desactiva el control.
- **credit_blocking**: monto máximo permitido.
- **amount_due**: deuda actual (related).

La orden de venta toma esos valores y decide si debe pedir aprobación.

---

### 2. Validación al confirmar

Al presionar **Confirmar** en una venta:

1. El sistema suma la **deuda actual del cliente** (`amount_due`) + **total de la orden**.
2. Si ese total supera el **límite de bloqueo** del cliente.
3. Se abre un **wizard** que muestra el exceso y permite “Enviar para aprobación”.

Si no lo supera, la orden se confirma normalmente.

---

### 3. Estado extra

Se agrega un estado en la orden:

- **`sales_approval`** → “Aprobación de Crédito”.

Mientras la orden está en ese estado, no se confirma.  
Un gerente puede aprobar o rechazar desde la propia orden.

---

### 4. Notificaciones internas

Cuando el vendedor envía a aprobación:

- Se deja una nota en el chatter (sin enviar correo).
- Se suscribe a los usuarios “gerentes”.
- Y se crea una **actividad** “Revisar aprobación de crédito” para esos gerentes.

Cuando el gerente **aprueba** o **rechaza**:

- Se deja otra nota en el chatter.
- Y se crea una **actividad** para el **vendedor** avisando que ya puede confirmar o que fue rechazado.

Así cada lado recibe su alerta.

---

### 5. Permisos

Las acciones de aprobar/rechazar validan que el usuario pertenezca al grupo estándar:

- **`base.group_erp_manager`** (Administración / Permisos de acceso).

Podés ampliar esto a otros grupos si lo necesitás.

---

## 🧭 Flujo de uso

1. Vendedor crea una cotización.
2. La intenta confirmar, pero el cliente supera su crédito → aparece el wizard.
3. Vendedor pulsa **“Enviar para Aprobación de Crédito”**.
4. La orden pasa a estado **Aprobación de Crédito** y se crean actividades para los gerentes.
5. Un gerente entra a la orden y pulsa **Aprobar** o **Rechazar**.
6. Se crea una actividad para el vendedor con el resultado.
7. Si fue aprobada, el vendedor confirma la orden normalmente.

---

## 🐞 Notas sobre entornos de prueba

En bases “neutralizadas” (por ejemplo, Odoo.sh de prueba) el módulo publica los mensajes en modo **silencioso**, sin intentar enviar correo, para evitar el popup de “configure la dirección de correo del remitente”.

---

## 📦 Instalación

1. Copiar el módulo en la carpeta de addons.
2. Actualizar lista de aplicaciones.
3. Instalar el módulo.
4. Configurar en los contactos el límite de crédito.
5. Asignar el grupo **Administración / Permisos de acceso** a quienes deban aprobar.

---

**Autor:** Abel Alejandro Acuña  
**Estado:** Estable ✅  
**Última actualización:** Noviembre 2025
