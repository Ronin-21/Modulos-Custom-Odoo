# POS Order Ticket (Heladería) - Comanda / Ticket de Pedido (Odoo 18)

**Módulo:** `pos_order_ticket`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Point of Sale  
**Dependencias:** `point_of_sale`  
**Autor:** Abel Alejandro Acuña — https://ronin-webdesign.vercel.app/

Agrega en el POS un botón para **imprimir un ticket de pedido / comanda** (sin precios), ideal para cocina, barra o elaboración (ej: heladería).

---

## ✅ Funcionalidades

- Botón **“Comanda”** (o **“Reimprimir”** si ya se imprimió) en la **Pantalla de Productos**, junto al botón de Pago.
- Imprime un ticket **sin importes**, con:
  - título **PEDIDO**
  - indicador **DUPLICADO** si es reimpresión
  - **Orden** (nombre/uid)
  - **Fecha**
  - **Líneas**: `cantidad x producto` + **Observación** (nota de línea) si existe
- Si hay un servicio de impresión disponible en POS:
  - usa `pos_printer.printReceipt()` o `printer.printHtml()`
- Si no hay printer configurado, hace **fallback** a imprimir por navegador (abre una ventana y ejecuta `window.print()`).

---

## ⚙️ Configuración

1. Ir a **Punto de Venta → Configuración → Punto de Venta**
2. Abrir el POS deseado
3. Activar: **“Habilitar ticket de pedido (comanda)”**

> Nota: el checkbox queda **solo lectura** si hay una sesión activa (`has_active_session`).

---

## 🧾 Uso en el POS

1. Abrí el POS (sesión)
2. Armá la orden con productos
3. Presioná **Comanda**
4. Si ya imprimiste esa orden, el botón cambia a **Reimprimir** (marca `order.uiState.order_ticket_printed = true`).

---

## 🧩 Qué modifica (técnico)

### Backend

- Agrega en `pos.config`:
  - `enable_order_ticket` (Boolean)
- Asegura que el POS lo reciba en la carga de sesión:
  - `_loader_params_pos_config` agrega el field en los loaders

### Frontend (POS)

- Patch de `ActionpadWidget` para:
  - mostrar el botón según `pos.config.enable_order_ticket`
  - generar el HTML del ticket con `renderToElement()`
  - mandar a imprimir usando el servicio disponible

Archivos principales:

- `static/src/js/order_ticket_button.js`
- `static/src/xml/order_ticket_templates.xml`
- `views/pos_config_view.xml`

Assets:

- `point_of_sale._assets_pos`

---

## ✏️ Personalización rápida

En el template del ticket hay datos comentados (cajero/cliente).  
Si querés mostrarlos, podés descomentar en:

`static/src/xml/order_ticket_templates.xml`

```xml
<!-- <div><strong>Cajero:</strong> <t t-esc="header.cashier"/></div>
<t t-if="header.partner">
    <div><strong>Cliente:</strong> <t t-esc="header.partner"/></div>
</t> -->
```
