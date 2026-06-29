# Presupuestos y Facturas en ticket térmico 80mm (Ticket) — Odoo 18

**Módulo:** `report_sale_invoice_thermal_80mm`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Sales/Accounting  
**Autor:** Abel Alejandro Acuña  
**Dependencias:** `web`, `sale_management`, `account`

Reportes PDF en formato **térmico 80mm** (estilo ticket) para:

- **Presupuesto 80mm** → `sale.order`
- **Factura 80mm** → `account.move`

Diseño compacto, tipografía monoespaciada y estilos **inline** para que el render de PDF sea consistente en wkhtmltopdf.

---

## ✅ Qué incluye

### 1) Reporte “Presupuesto 80mm” (Ventas)

Impresión tipo ticket para `sale.order` con:

- Encabezado empresa (nombre, dirección, **CUIT** si existe)
- Datos: fecha, validez, vendedor
- Cliente (nombre + datos básicos)
- Líneas: descripción + total de línea + detalle `cantidad x unitario`
- Totales: subtotal, impuestos, total
- Mensaje final “Gracias por su compra”

### 2) Reporte “Factura 80mm” (Contabilidad)

Impresión tipo ticket para `account.move` (facturas) con:

- Encabezado empresa (incluye **Responsabilidad AFIP** si el campo existe en la localización AR)
- Datos: fecha, vendedor
- Cliente (nombre + datos básicos)
- Líneas: descripción + **subtotal (sin impuestos)** + detalle `cantidad x unitario`
- Totales: subtotal, impuestos, total

#### Bloque fiscal (si existe localización AR)

Si el comprobante tiene campos AFIP, muestra:

- **CAE** + **Vto CAE**
- **QR AFIP** (más chico, 24mm aprox)

> El bloque fiscal se renderiza **solo si existen** los campos y/o valores (no fuerza dependencias de `l10n_ar`).

---

## 🧾 Cómo imprimir

### Presupuesto 80mm

1. Ir a **Ventas → Pedidos / Presupuestos**
2. Abrir un presupuesto
3. **Imprimir → “Presupuesto 80mm”**

### Factura 80mm

1. Ir a **Contabilidad → Proveedores/Clientes → Facturas** (según tu flujo)
2. Abrir una factura
3. **Imprimir → “Factura 80mm”**

---

## 📐 Formato de papel (Paperformat)

El módulo agrega un paperformat:

- **Térmico 80mm (Rollo)**
- `page_width = 80`
- `page_height = 297` (altura “moderada” para evitar que el visor haga _fit page_ y achique todo)
- Márgenes:
  - top/bottom: 2mm
  - left/right: 0mm
- `disable_shrinking = True`
- `dpi = 90`

Además, el ticket usa un contenedor `.thermal-page` de **76mm** con padding lateral para que el contenido no pegue al borde.

---

## 🧠 Detalles técnicos

### Estilos inline (sin assets externos)

Los estilos van embebidos dentro del QWeb (`<style>`), incluyendo:

- reset de márgenes/padding del layout
- tipografía `"DejaVu Sans Mono"`
- separadores y tablas compactas
- QR reducido (24mm)

### QR AFIP por `/report/barcode`

Se agrega un helper en `account.move`:

- `o._thermal_afip_qr_src(width, height)`

Genera una URL absoluta a `/report/barcode` usando `web.base.url`, ideal para wkhtmltopdf.

---

## 🧪 Tips / Troubleshooting

- **El ticket sale “muy chico” (escalado):** este módulo ya activa `disable_shrinking` y ajusta DPI. Si aún se escala, revisá el paperformat y que no haya otro módulo heredando el mismo reporte/paperformat.
- **Tickets largos “cortados”:** el paperformat usa altura 297mm. Si tenés pedidos con muchas líneas, aumentá `page_height` en el paperformat (por ejemplo 600/1000) o aceptá que salga en más de una página.
- **No aparece QR/CAE:** solo se muestra si el comprobante tiene valores en `l10n_ar_afip_auth_code` / `l10n_ar_afip_qr_code` (localización AR).

---
