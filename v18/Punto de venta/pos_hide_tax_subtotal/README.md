# pos_hide_tax_subtotal

Módulo para Odoo 18 (Community / Enterprise) que **oculta las líneas de Subtotal e IVA** en:

- ✅ Ticket no fiscal (POS Receipt)
- ✅ Precuenta / Cuenta del cliente (Bill Screen)

## Instalación

1. Copiar la carpeta `pos_hide_tax_subtotal` dentro del directorio de addons de tu instancia:
   ```
   /odoo/addons/pos_hide_tax_subtotal
   ```
   o donde tengas configurado `addons_path` en tu `odoo.conf`.

2. Reiniciar el servidor Odoo:
   ```bash
   sudo systemctl restart odoo
   # o
   ./odoo-bin -c odoo.conf
   ```

3. Desde el backend: **Aplicaciones → Actualizar lista de aplicaciones**.

4. Buscar `POS Ocultar Subtotal e IVA` e instalar.

5. Si los cambios no se ven, limpiar assets:
   ```
   Configuración → Técnico → Interfaz de usuario → Activos web → Regenerar
   ```
   O en modo debug: `?debug=assets` y limpiar caché del navegador.

## Compatibilidad

| Odoo | Estado |
|------|--------|
| 18.0 | ✅ Soportado |
| 17.0 | ⚠️ No probado |

Dependencias: `point_of_sale`, `l10n_ar`

## Troubleshooting

Si después de instalar el bloque sigue visible:

1. **Verificar el nombre exacto de la clase CSS** del bloque en tu versión:
   - Abrir el POS en modo debug (`?debug=assets`)
   - Inspeccionar el elemento (F12) y buscar la clase del `<div>` que contiene "Subtotal" e "IVA"
   - Agregar esa clase al archivo `static/src/css/pos_hide_tax.css`

2. **Verificar el nombre del template QWeb**:
   - En Odoo 18, el template puede llamarse `point_of_sale.OrderReceipt` u otro nombre según la versión exacta.
   - Buscar en `/odoo/addons/point_of_sale/static/src/` el archivo `.xml` que contiene `pos-receipt-taxes`.

## Estructura del módulo

```
pos_hide_tax_subtotal/
├── __init__.py
├── __manifest__.py
└── static/
    └── src/
        ├── css/
        │   └── pos_hide_tax.css          ← Fallback CSS
        └── xml/
            ├── pos_receipt_override.xml  ← Override ticket no fiscal
            └── pos_bill_override.xml     ← Override precuenta
```
