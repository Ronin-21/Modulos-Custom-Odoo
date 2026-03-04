# Gestor de Plantillas de Reportes Personalizadas (Odoo 18)

**Módulo:** `report_custom_templates`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Technical  
**Autor:** Abel Alejandro Acuña  
**Dependencias:** `base`, `sale`, `purchase`, `account`, `l10n_ar`, `l10n_latam_invoice_document`, `mrp`

Sistema centralizado para **personalizar reportes PDF** desde la interfaz, con configuración **por empresa** (multi-compañía): colores, logo por texto y ajustes por tipo de reporte.

---

## ✅ Funcionalidades principales

### 1) Configuración por empresa (multi-company)

Crea y mantiene una configuración única por empresa en el modelo:

- `report.template.config`

Incluye:

- **Texto del logo** (ej: “AI”)
- **Colores** (HEX):
  - Primario
  - Secundario
  - Fondo de header
  - Acento
- Flags y selectores (UI) para MRP / Ventas / Compras / Pagos

📌 Restricción: **solo 1 configuración activa por empresa** (SQL constraint `unique(company_id)`).

---

### 2) App de Ajustes (sin tocar código)

Agrega una sección en **Ajustes**:

**Ajustes → Plantillas de Reportes**

Desde ahí se puede editar:

- Logo por texto
- Paleta de colores
- Activar/desactivar opciones (según módulo)
- Elegir “plantilla” (clean/simple/standard) para algunos reportes

> Nota: la configuración se guarda en `report.template.config`. Si no existe para la empresa, se **crea automáticamente**.

---

### 3) Facturas (Argentina) + ocultar datos fiscales por diario

Personaliza el reporte de factura argentino heredando:

- `l10n_ar.report_invoice_document`

Incluye:

- Un título “Factura <número>”
- Posibilidad de **ocultar datos fiscales** (CUIT, QR, etc.) según el diario contable

Para eso agrega en **Diarios** (`account.journal`):

- **Mostrar datos fiscales en el PDF** (`show_fiscal_data`)

✅ Útil para diarios tipo **“Factura X”** o comprobantes internos.

---

### 4) Cabecera personalizada para Ventas (Cotizaciones / Pedidos)

Personaliza el layout del reporte usando:

- `web.external_layout_wave`

Permite en **Ventas**:

- Usar **logo de texto** (según configuración) o el **logo imagen** de la compañía
- Aplicar colores configurados a la cabecera

---

### 5) MRP (Manufactura)

Personaliza reportes heredando:

- `mrp.report_mrporder` (Orden de Manufactura)
- `mrp.report_mrp_production_components` (Componentes)

Incluye:

- Banner/títulos con colores dinámicos
- Bloques de información con fondo configurable
- Tabla de componentes con estilos

---

### 6) Recibo de Pago + tabla de cheques (opcional)

Hereda:

- `account.report_payment_receipt_document`

Agrega una tabla **“Cheques Utilizados”** al final del recibo si:

- está habilitado en configuración (`show_payment_checks`)
- y existen cheques (l10n_latam_check)

---

## 🔐 Seguridad / Accesos

Incluye permisos para el modelo `report.template.config`:

- **Usuarios internos (`base.group_user`)**: solo lectura
- **Sistema (`base.group_system`)**: lectura/escritura/crear/eliminar

Además agrega un menú técnico:

- **Ajustes (Administración) → Plantillas de Reportes** (solo sistema)

---

## ⚙️ Configuración inicial

Incluye un registro por defecto para la empresa principal:

- `AI` como logo_text
- Paleta inicial (primario `#FF6B55`, etc.)
- Ventas y Pagos activos por defecto (según data)

Archivo:

- `data/report_template_data.xml`

---

## 🧪 Pruebas rápidas

### A) Factura X sin datos fiscales

1. Ir a **Contabilidad → Configuración → Diarios**
2. Abrir el diario “Factura X”
3. Desmarcar **Mostrar datos fiscales en el PDF**
4. Imprimir una factura de ese diario → no debe mostrar bloque fiscal/QR

### B) Ventas con logo texto

1. Ir a **Ajustes → Plantillas de Reportes**
2. Definir **Texto del Logo** (ej: “AI”) y colores
3. Imprimir una **Cotización/Pedido** → la cabecera debe usar ese texto (si está en modo texto)

### C) Recibo de pago con cheques

1. Registrar un pago con cheques (l10n_latam_check)
2. Imprimir recibo → aparece tabla “Cheques Utilizados” (si está habilitado)

---

## ⚠️ Notas importantes

- En esta versión, la lógica de “activar/desactivar” por módulo está **implementada principalmente en Ventas** (cabecera condicional).  
  En MRP/Recibos, las plantillas se aplican por herencia del QWeb; el selector “clean/simple/standard” está disponible en la UI pero puede requerir variantes adicionales para que cambie efectivamente el diseño.
- El módulo depende de localización AR (`l10n_ar`) y documento latam (`l10n_latam_invoice_document`) porque las plantillas se apoyan en esos reportes.

---
