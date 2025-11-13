# Categorías Multi-Empresa

Módulo para Odoo 18.0 que permite gestionar categorías de POS y Producto por empresa en entornos multi-compañía.

## Características

### 🏢 Gestión por Empresa

- Asigna categorías de Punto de Venta a empresas específicas
- Asigna categorías de Producto/Inventario a empresas específicas
- Las categorías sin empresa asignada son visibles para todas

### 🔒 Seguridad Automática

- Filtrado automático según la empresa activa del usuario
- Reglas de dominio que garantizan el aislamiento de datos
- Compatible con permisos multi-empresa de Odoo

### 📊 Vistas Mejoradas

- Campo "Empresa" visible en formularios y listas
- Integración transparente con vistas estándar de Odoo
- Sin modificaciones en la lógica de negocio existente

## Instalación

1. Copia el módulo en tu directorio de addons:

   ```bash
   cp -r pos_category_company /path/to/odoo/addons/
   ```

2. Actualiza la lista de aplicaciones en Odoo:

   - Modo desarrollador > Aplicaciones > Actualizar lista de aplicaciones

3. Busca "Categorías Multi-Empresa" e instala el módulo

## Configuración

No requiere configuración adicional. El módulo funciona automáticamente después de la instalación.

### Asignar Empresa a Categorías

#### Categorías POS

1. Ve a **Punto de Venta > Configuración > Categorías de Productos**
2. Abre o crea una categoría
3. Selecciona la empresa en el campo "Empresa"

#### Categorías de Producto

1. Ve a **Inventario > Configuración > Categorías de Producto**
2. Abre o crea una categoría
3. Selecciona la empresa en el campo "Empresa"

## Uso

### Comportamiento del Filtrado

- **Con empresa asignada**: La categoría solo es visible para usuarios de esa empresa
- **Sin empresa asignada**: La categoría es visible para todas las empresas
- **Cambio de empresa**: Al cambiar de empresa activa, las categorías se filtran automáticamente

### Casos de Uso

1. **Empresas con diferentes líneas de productos**

   - Empresa A: Categorías de electrónica
   - Empresa B: Categorías de alimentos

2. **Separación por unidad de negocio**

   - Sucursal Norte: Sus propias categorías
   - Sucursal Sur: Sus propias categorías

3. **Gestión de franquicias**
   - Cada franquicia con su catálogo independiente

## Estructura del Módulo

```
pos_category_company/
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   ├── pos_category.py
│   └── product_category.py
├── views/
│   ├── pos_category_views.xml
│   └── product_category_views.xml
└── security/
    ├── ir.model.access.csv
    └── category_rules.xml
```

## Dependencias

- `point_of_sale`: Módulo de Punto de Venta
- `product`: Gestión de productos
- `sale_management`: Gestión de ventas

## Compatibilidad

- ✅ Odoo 18.0 (Community & Enterprise)
- ✅ Multi-compañía
- ✅ Compatible con módulos de inventario
- ✅ Compatible con módulos de ventas

## Soporte

Para soporte técnico o consultas:

- **Autor**: Alderete Informática y Soporte
- **Website**: https://www.aldereteinformatica.com

## Licencia

LGPL-3

## Changelog

### Version 18.0.1.0.0 (2025-10-16)

- Versión inicial
- Soporte para categorías POS
- Soporte para categorías de producto
- Reglas de seguridad multi-empresa
