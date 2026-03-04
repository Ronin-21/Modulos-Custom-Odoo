# POS Métodos de Pago con Descuentos y Recargos (Odoo 18)

**Módulo:** `pos_payment_custom`  
**Versión:** 18.0.1.0  
**Licencia:** LGPL-3  
**Categoría:** Sales / Point of Sale  
**Dependencias:** `point_of_sale`  
**Autor:** Abel Alejandro Acuña

Este módulo permite configurar **descuentos y recargos** según el **método de pago** del POS, incluyendo:

- **Descuento** (porcentaje fijo por método)
- **Recargo por tarjeta y plan de cuotas** (por tarjeta + opción de cuotas)
- Captura obligatoria de **N° de cupón** (formato `123-1234`) cuando corresponda
- Reportes y vistas para auditar cupones, tarjetas y planes
- Botón “Ticket 80mm” en el cierre de sesión (reporte térmico)

---

## ✅ Funcionalidades principales

### 1) Descuento por método de pago (porcentaje fijo)

En cada **Método de pago** (`pos.payment.method`) podés activar:

- **Aplicar descuento/recargo**
- **Tipo de ajuste:** `Descuento`
- \*\*Porcentaje de descuento (%)`

📌 **Cómo aplica el descuento en el POS:**  
El descuento se aplica como **descuento (%) en las líneas del pedido** (no crea un producto de descuento).  
El módulo guarda y restaura descuentos previos de líneas cuando corresponde (para no pisar descuentos existentes en líneas no afectadas).

---

### 2) Recargo por tarjeta + plan de cuotas

En cada **Método de pago** (`pos.payment.method`) podés activar:

- **Aplicar descuento/recargo**
- **Tipo de ajuste:** `Recargo`
- **Producto de recargo** (línea extra en el pedido)

Luego, dentro de la pestaña **Tarjetas y Cuotas**:

- Crear una o más **Tarjetas** (Visa, Master, Naranja, etc.)
- Para cada tarjeta, crear **Opciones de cuotas** con:
  - **Cuotas**
  - **Recargo (%)**
  - **Nombre del plan** (ej: “3 Cuotas (15%)”)
  - Activo / Secuencia

📌 **Cómo aplica el recargo en el POS:**  
El recargo se agrega como una **línea adicional** usando el **Producto de recargo** configurado (ej: “Recargo POS”), con el importe calculado según el porcentaje elegido.

---

### 3) Número de cupón (obligatorio por tarjeta)

Cada tarjeta puede marcarse como:

- **Requiere número de cupón**

En el POS, al elegir esa tarjeta, se habilita el campo de cupón con máscara:

- **Formato:** `123-1234`

Se guarda por **línea de pago** en `pos.payment.coupon_number`.

---

### 4) Auditoría y consultas (Backoffice)

El módulo agrega:

- En **Pedidos POS**: campo calculado **“Nº Cupón”** (concatena cupones de pagos del pedido).
- Botón en pedido: **“Recalcular Cupones”** (útil para órdenes antiguas/importadas).
- Menú **Punto de Venta → Pedidos con Cupón**
- Menú **Punto de Venta → Cupones de Pago** (lista de pagos con cupón, tarjeta, plan, importe, sesión)

Además, en el árbol de **Pagos** dentro del pedido POS muestra columnas opcionales:

- **Tarjeta**
- **Plan**
- **Nº Cupón**

---

## 🧾 Reportes / Cierre de caja

### 1) Detalle por método + tarjeta + plan (cierre POS)

En el popup de **cierre de sesión** se agrega un desglose de pagos con tarjeta:

- Método de pago
- Tarjeta
- Plan
- Cantidad de transacciones
- Total
- Cupones detectados

### 2) Botón “Ticket 80mm”

En el cierre de sesión aparece un botón:

- **Ticket 80mm**

Descarga un PDF térmico usando el reporte:

- `/report/pdf/pos_payment_custom.report_saledetails_80mm/<session_id>`

Incluye también un **paperformat 80mm** (ancho 80, márgenes 0).

---

## ⚙️ Configuración

### A) Configurar métodos de pago

Ruta: **Punto de Venta → Configuración → Métodos de Pago**

1. Activar **Aplicar descuento/recargo**
2. Elegir **Tipo de ajuste**
3. Si es **Descuento**:
   - Completar **Porcentaje de descuento (%)**
4. Si es **Recargo**:
   - Elegir **Producto de recargo**
   - Configurar **Tarjetas** y **Opciones de cuotas**

📌 Incluye botón:

- **Crear/Traer producto Recargo**  
  Crea (por compañía) un producto servicio “Recargo POS” y lo asigna al método.

---

## 🧠 Cómo guarda los datos (campos)

### En `pos.payment`

- `coupon_number` (N° cupón)
- `card_name` (Tarjeta)
- `installments` (Cuotas)
- `installment_percent` (Recargo %)
- `installment_plan_name` (Plan)

### En `pos.order`

- `adjustment_type` (discount/surcharge/none)
- `adjustment_amount`
- `adjustment_percent`
- `coupon_numbers` (resumen “123-1234, 555-9999”)

---

## 🧩 Detalles técnicos relevantes

- Incluye un **post_init_hook** que crea/asegura el producto “Recargo POS” por compañía (si hace falta) y lo asigna a métodos de recargo que estén incompletos.
- Asegura que el **producto de recargo** esté disponible en POS y que entre en el dominio de productos cargados por el POS.
- En el POS:
  - Agrega UI en `PaymentScreen` para seleccionar tarjeta/plan y cargar cupón.
  - Agrega columna **Cupón** en `TicketScreen`.
  - Agrega desglose de tarjetas en el cierre y botón de reporte **80mm**.

---

## 🧪 Prueba rápida (checklist)

1. Configurar un método “Efectivo” como **Descuento 10%**
2. Abrir POS → crear orden → pagar con Efectivo → verificar que se aplica el 10% a líneas (descuento en líneas).
3. Configurar un método “Tarjeta” como **Recargo**:
   - Asignar producto recargo (o botón Crear/Traer)
   - Crear tarjeta “Visa” con opción “3 cuotas 15%”
4. En POS → pagar con Tarjeta → elegir Visa + plan → verificar:
   - se agrega línea de recargo en el pedido
   - se guardan tarjeta/plan/cupón en el pago
5. En backoffice:
   - Ver **Pedidos con Cupón**
   - Ver **Cupones de Pago**
   - Imprimir **Ticket 80mm** desde cierre de sesión

---
