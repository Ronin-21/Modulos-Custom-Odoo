# Report Sale & Invoice Cleaner (AR)

Encabezados “limpios” para **cotizaciones** y opción de **ocultar datos fiscales** en **facturas** según el diario, manteniendo la plantilla argentina de Odoo (`l10n_ar` / `l10n_latam_invoice_document`).

> ✅ Probado en **Odoo 18** (Enterprise), con **l10n_ar** y **l10n_latam_invoice_document**.

---

## ¿Qué hace?

- **Sale Order / Cotización**

  - Reemplaza el _header wave_ por uno **minimal** con la marca (“PM” por defecto).
  - En la dirección del cliente muestra **solo** nombre, domicilio y **teléfono** (sin CUIT, mail, etc.).
  - Cambia el título del reporte a **“Presupuesto <N°>”**.

- **Factura (account.move)**
  - Agrega un **check** en el **Diario**: `Mostrar datos fiscales en el PDF` (`show_fiscal_data`).
  - Si el diario **tiene destildado** el check (p.ej. _Factura X_ / _Comprobante interno_):
    - Header simplificado (sin CUIT/IIBB/CAE/QR).
    - **Oculta**: bloque de información fiscal, **QR** y **leyenda AFIP**.
    - Muestra un total **genérico**.
  - Si el diario **tiene tildado** el check (p.ej. _Factura Electrónica_):
    - Se mantiene el reporte **oficial AR** con todos los datos (CAE, QR, leyendas).

> ⚠️ No altera la lógica de EDI ni la comunicación con AFIP. Solo afecta lo **impreso**.

---

## Estructura
