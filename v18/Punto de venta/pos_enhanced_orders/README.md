# POS Enhanced Orders

Módulo unificado para Odoo 18 que combina:

- **Pantalla de tickets mejorada** con columnas configurables, badges de estado de factura, métodos de pago y filtros inteligentes.
- **Backport de mejoras de facturación del POS de Odoo 19** con bloqueo defensivo, reconciliación avanzada de pagos, wizard de cierre y validación fiscal argentina.

## Funcionalidades

### Pantalla de tickets (TicketScreen)

- Insignias de estado de factura en tiempo real (Borrador, Confirmada, Cancelada, Sin factura).
- Columna de métodos de pago usados en cada orden.
- Info fiscal visual en el número de recibo.
- Filtros por estado de factura desde el dropdown nativo.
- Botón para confirmar facturas borrador directamente desde el POS.
- Columnas totalmente configurables por POS (fecha, recibo, orden, cliente, cajero, total, estado, mesa).

### Facturación robusta (backport Odoo 19)

- Bloqueo fuerte en `sync_from_ui`: si la factura no queda publicada o sin autorización fiscal, la orden no se valida y se hace rollback completo.
- Reconciliación avanzada de pagos POS con la factura (4 estrategias escaladas: re-link, búsqueda de huérfanos, creación nativa, reconstrucción total).
- Wizard interactivo al cierre de sesión para emitir o eliminar facturas borrador pendientes.
- Limpieza automática de facturas borrador cuando el wizard está desactivado.
- Validación genérica de CAE/AFIP para facturas electrónicas argentinas.
- Errores reales del backend mostrados en el POS (en lugar de mensajes genéricos).
- Reimpresión de eticket electrónico desde TicketScreen (cuando `l10n_ar_pos_eticket` está instalado).

## Configuración

### Columnas del TicketScreen

Ir a: **Punto de Venta → Configuración → [Tu POS] → Tickets (Columnas y Botones)**

Activar/desactivar:
- Cualquier columna estándar de Odoo (Fecha, Recibo, Orden, Cliente, Cajero, Total, Estado, Mesa)
- Columna de estado de factura
- Columna de métodos de pago
- Botón de confirmación de factura
- Modificación visual del número de recibo

### Facturación al cierre

Ir a: **Punto de Venta → Configuración → [Tu POS] → Facturación al cierre**

- **Confirmación de facturas borrador al cierre**: si está activo, al cerrar una sesión con facturas borrador se abre un wizard para emitirlas o eliminarlas. Si está desactivado, se eliminan automáticamente.

También disponible desde: **Ajustes → Punto de Venta → Confirmación de facturas borrador al cierre**.

## Instalación

1. Copiar la carpeta `pos_enhanced_orders` dentro del `addons_path`.
2. Actualizar lista de apps.
3. Instalar el módulo.
4. Reiniciar el servicio y limpiar assets si corresponde.

## Notas técnicas

- El wizard de confirmación trabaja sobre las órdenes de la sesión que todavía tienen `account_move` en `draft`.
- La verificación de CAE es genérica: si existe el campo `l10n_ar_afip_auth_code`, el addon exige que esté informado para considerar la factura como emitida.
- Los campos `invoice_state`, `invoice_name` y `payment_method_names` son stored computed para evitar RPCs extra en el frontend.
- La reconciliación al confirmar desde el botón del TicketScreen usa primero la lógica robusta del v19 y cae a una reconciliación básica como fallback.

## Requisitos

- Odoo 18.0 Community o Enterprise
- Módulo Punto de Venta (`point_of_sale`)
- Módulo Contabilidad (`account`)

## Historial de versiones

### 18.0.2.0.0
- Unificación de `pos_enhanced_orders` y `pos_v19_invoice_guard` en un solo módulo.
- Reconciliación robusta del v19 integrada al botón "Confirmar factura" del TicketScreen.
- Configuración consolidada en `pos.config` con acceso desde res.config.settings.

### 18.0.1.0.0
- Versión inicial de pos_enhanced_orders (columnas configurables, badges, filtros).


### 18.0.2.1.0
- Revisión y reunificación del módulo sobre la última base disponible.
- Se restituye el flujo de cierre del POS usando el manejo de `handleClosingError()` del backport v19 para respetar la prohibición de cierre cuando existen facturas borrador.
