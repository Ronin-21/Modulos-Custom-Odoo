# Reporte de Venta + Factura “Cleaner” (Odoo 18)

**Módulo:** `report_sale_invoice_cleaner`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Sales / Accounting  
**Dependencias:** `sale_management`, `account`

Plantillas QWeb para imprimir **Pedido de Venta** y **Factura** con un diseño **más limpio y compacto**, orientado a uso práctico (menos ruido visual, mejor jerarquía y tablas más claras).

---

## ✅ Qué incluye

### 1) Reporte de Pedido de Venta (sale.order)

- Encabezado compacto
- Bloque de cliente y datos del documento más claro
- Tabla de líneas con layout limpio
- Totales destacados

### 2) Reporte de Factura (account.move)

- Encabezado limpio
- Datos del cliente y comprobante bien agrupados
- Tabla de líneas simplificada
- Totales y condiciones con menos “relleno”

---

## ⚙️ Instalación

1. Copiar el módulo `report_sale_invoice_cleaner` en tus addons.
2. Actualizar lista de Apps.
3. Instalar el módulo.
4. Imprimir:
   - **Ventas → Pedidos → Imprimir**
   - **Contabilidad → Facturas → Imprimir**

---

## 🧩 Cómo funciona (técnico)

El módulo se basa en **herencias de QWeb** sobre los reportes estándar de Odoo:

- Reemplaza/ajusta secciones del template original (header, table, totals)
- Aplica CSS propio (si corresponde) para spacing y tipografías

---

## 🧪 Prueba rápida

1. Crear un pedido de venta con varias líneas.
2. Imprimir → verificar que el documento salga más “compacto”.
3. Crear una factura con varias líneas.
4. Imprimir → verificar tabla, totales y cabecera.

---

## ⚠️ Notas

- No modifica lógica de negocio: solo **presentación** de reportes.
- Si tenés otros módulos que hereden los mismos templates, puede haber conflictos de prioridad/herrencia; en ese caso se ajusta el `inherit_id` o el orden.

---
