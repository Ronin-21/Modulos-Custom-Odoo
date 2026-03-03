# POS Pantalla de Ordenes Mejorada

![Versión Odoo](https://img.shields.io/badge/Odoo-18.0-blue)
![Licencia](https://img.shields.io/badge/License-LGPL--3-green)

Mejora completa de la pantalla de tickets/órdenes del Punto de Venta de Odoo con seguimiento avanzado de facturas, visualización de métodos de pago y columnas totalmente configurables.

## 🎯 Funcionalidades

### Gestión de Facturas

- **Insignias (badges) de estado de factura en tiempo real** con codificación por color:
  - 🟢 Confirmada (Publicada / Posted)
  - 🟡 Borrador (Draft)
  - 🔴 Cancelada (Cancelled)
  - ⚪ Sin factura (No Invoice)
- **Confirmación de factura con un clic** directamente desde el POS
- **Conciliación automática de pagos** al confirmar
- **Información fiscal visual** en los números de comprobante
- **Filtros por estado de factura** para búsquedas rápidas

### Seguimiento de Pagos

- **Columna de métodos de pago** mostrando todos los tipos utilizados
- Vista rápida de: Efectivo, Tarjeta, Transferencias, etc.
- Cálculo automático desde los pagos del POS

### Interfaz Configurable

- **Activar/desactivar cualquier columna** desde la configuración
- **Configuración por cada POS** (cada terminal puede tener un set distinto)
- Diseño **adaptable a móviles** (responsive)

### Filtrado Inteligente

- Filtrar por estado de factura (Sin factura, Borrador, Confirmada, Cancelada)
- Funciona junto a los filtros nativos de Odoo
- Filtrado del lado del cliente (¡rápido!)

## 📸 Capturas

![Columna Estado de Factura](static/description/screenshot_invoice_column.png)
![Métodos de Pago](static/description/screenshot_payment_column.png)
![Filtros](static/description/screenshot_filters.png)
![Botón Confirmar](static/description/screenshot_confirm_button.png)

## 🚀 Instalación

1. Descargar o clonar este módulo dentro del directorio de addons de Odoo:
   ```bash
   cd /path/to/odoo/addons
   git clone https://github.com/your-repo/pos_enhanced_ticket.git
   ```
