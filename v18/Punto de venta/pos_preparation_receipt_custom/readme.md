# POS - Recibo de Preparación Personalizado (Odoo 18)

**Módulo:** `pos_preparation_receipt_custom`  
**Versión:** 18.0.1.0.0  
**Licencia:** LGPL-3  
**Categoría:** Point of Sale  
**Dependencias:** `point_of_sale`

Personaliza el **recibo de preparación / comanda** del POS (el que se imprime para cocina/barra) agregando información útil y ajustando el diseño.

---

## ✅ Qué hace

- Extiende el ticket/recibo de **preparación** del POS (kitchen ticket).
- Agrega en el encabezado:
  - **Fecha**
  - **Número de orden**
  - **Mozo / Responsable** (si existe en la orden)
  - **Mesa** (si existe)
- Ajusta el formato para impresión (tipografía, espacios y alineación) mediante CSS/plantillas.

> No cambia el ticket fiscal o el recibo de cliente: solo el de **preparación**.

---

## 🧾 Información incluida en la comanda

En general, el recibo muestra:

- Título de preparación
- Orden / referencia
- Fecha/Hora
- Mesa / mozo (si aplica)
- Detalle de líneas:
  - cantidad
  - producto
  - notas / atributos (si existen)

---

## ⚙️ Instalación

1. Copiar el módulo `pos_preparation_receipt_custom` en tus addons.
2. Actualizar lista de Apps.
3. Instalar el módulo.
4. Abrir una sesión de POS y probar la impresión de preparación.

---

## 🧩 Cómo funciona (técnico)

- Hereda/patch de plantillas QWeb/OWL del POS para el **preparation receipt**.
- Incluye assets en `point_of_sale._assets_pos` para:
  - template XML
  - estilos CSS (si aplica)

Archivos típicos:

- `static/src/xml/*.xml`
- `static/src/css/*.css` o `static/src/scss/*.scss`

---

## 🧪 Prueba rápida

1. Abrí el POS.
2. Creá una orden con productos que impriman preparación (según tu configuración de impresoras/productos).
3. Enviá a preparación / imprimí comanda.
4. Verificá que aparezcan:
   - Fecha
   - Orden
   - Mesa y mozo (si tu flujo los usa)

---

## ⚠️ Notas

- Lo que aparezca exactamente (mesa/mozo) depende de si esos datos están presentes en la orden (por otros módulos o por configuración).
- Si tu POS usa múltiples impresoras/estaciones, el cambio aplica a todas las comandas del flujo estándar.

---
