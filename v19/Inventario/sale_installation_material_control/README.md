# Control de Materiales de Instalación (`sale_installation_material_control`)

Módulo Odoo 19 que agrega una capa de control sobre venta / proyecto / inventario para
gestionar **materiales de instalación** que se retiran y devuelven de forma parcial, calcular
el **consumo real** y facturar únicamente lo efectivamente utilizado.

## Problema que resuelve

Se vende una instalación (un producto servicio, ej. `INSTALACIONES`, + materiales stockables,
ej. `CAÑO COBRE`). El material no se consume de una sola vez: el instalador retira parcial,
devuelve sobrante, y el consumo real recién se conoce al cerrar la obra. Facturar el presupuesto
completo (100) cuando se usaron 70 es incorrecto; y el sobrante no es una devolución del cliente.

## Solución

```
Cantidad usada real      = Total retirado - Total devuelto
Cantidad a facturar      = Cantidad usada real
Cantidad liberada (cierre) = Cantidad presupuestada - Cantidad usada real
```

Al cerrar, la línea de venta se ajusta al consumo real (la cantidad original se conserva en
campos de trazabilidad) y el sobrante vuelve a stock libre.

## Flujo de stock

```
Confirmar (100)   Stock libre        -> Reservado Instalaciones
Retiro            Reservado          -> En Poder del Instalador
Devolución        En Poder Instalador-> Reservado Instalaciones
Cierre (used)     En Poder Instalador-> Cliente            (impacta qty_delivered/factura)
Cierre (sobrante) Reservado          -> Stock libre        (liberación)
```

Las líneas de material **no usan** la entrega nativa: el módulo gestiona todos sus movimientos
con tipos de operación propios. Sólo el movimiento de **Consumo** impacta `qty_delivered` y la
facturación de la venta, por lo que nunca se factura el presupuesto antes del cierre ni quedan
backorders pendientes.

## Detección de venta de instalación

- Producto con el check **Es servicio de instalación** (`product.template.is_installation_service`), o
- Check manual **Es instalación** en la orden de venta (`sale.order.is_installation_order`).

## Configuración

Inventario / Ventas → Ajustes → bloque **Materiales de Instalación**:

- Ajustar cantidad de venta al cerrar (por defecto **Sí**).
- Permitir cierre con material en poder del instalador (por defecto **No** → exige confirmación).
- Ubicaciones y tipos de operación por almacén (se crean automáticamente; se pueden ajustar).

## Seguridad

- **Usuario:** ve controles, retiros y devoluciones.
- **Responsable:** crea retiros y devoluciones (o cualquier usuario con el check
  *Puede validar materiales de instalación*).
- **Administrador:** cierra, reabre, cancela y configura.

## Dependencias

`sale_management`, `sale_stock`, `stock`, `project`, `sale_project`, `account`.

## Prueba funcional (100 / 70 / 30)

Venta con 100 de `CAÑO COBRE` → confirmar (control creado, 100 reservado). Retiro 50, devolución
10 (usado 40), retiro 60, devolución 30 (usado 70). Cerrar → venta queda en 70, original 100
conservado, 30 liberado a stock, factura por 70, sin backorders.

## Documentación en Odoo

- `static/description/index.html` — manual visible en **Aplicaciones** (qué hace, configuración,
  uso, ejemplo 100/70/30 y validaciones).
- `static/description/icon.png` — ícono propio de la app.
