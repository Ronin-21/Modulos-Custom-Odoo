# Total de Unidades Vendidas en Ventas (Odoo 18)

**Módulo:** `sales_total_units`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Sales  
**Dependencias:** `sale_management`

Agrega el cálculo de **Total de unidades** en Pedidos de Venta y Cotizaciones, mostrando cuántas unidades (sumatoria de cantidades) tiene el documento.

---

## ✅ Funcionalidades

### 1) Campo “Total de unidades” en Pedido/Cotización

En `sale.order` se agrega:

- **Total de unidades** (`total_units`) _(compute, store)_

Cálculo:

- suma de `product_uom_qty` de las líneas de venta
- ignora líneas que no deberían contar como unidades (p.ej. secciones/notas) según implementación estándar de sale.order.line

---

### 2) Visualización en la interfaz

Incluye herencia de vistas para mostrar el total en:

- Formulario de Pedido/Cotización
- (según versión del módulo) puede incluir también listado (tree) o kanban

---

## ⚙️ Instalación

1. Copiar el módulo `sales_total_units` en tus addons.
2. Actualizar lista de Apps.
3. Instalar el módulo.

---

## 🧪 Prueba rápida

1. Crear un presupuesto con varias líneas:
   - Producto A qty 2
   - Producto B qty 3
2. Guardar → **Total de unidades = 5**
3. Modificar cantidades → se recalcula automáticamente.

---

## ⚠️ Notas

- No afecta contabilidad ni stock: es solo un **indicador** para operación/comercial.
- Si usás unidades distintas (kg, metros), sigue sumando “cantidad” tal cual está en líneas (no convierte UoM).

---
