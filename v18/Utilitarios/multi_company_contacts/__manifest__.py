# -*- coding: utf-8 -*-
{
    "name": "Multi Empresa: Empresas permitidas (Contactos)",
    "version": "18.0.1.6.3",
    "category": "Contacts",
    "summary": "Empresas permitidas en Contactos y control de uso comercial en POS, Ventas, Compras y Contabilidad.",
    "description": """
Multi-empresa por 'Empresas permitidas' (Contactos)
==================================================

Agrega el campo 'Empresas permitidas' en Contactos (res.partner) y lo usa para limitar visibilidad/uso a las empresas
seleccionadas en el selector multi-empresa (arriba a la derecha).

También agrega una capa de uso comercial para diferenciar contactos comerciales de contactos internos/del sistema:

- Empresa / Sucursal del sistema.
- Usuario del sistema.
- Administrador del sistema.
- Comercial / Cliente-Proveedor.

El tipo de contacto carga presets por defecto. El bloqueo general "Ocultar en operaciones comerciales" es absoluto:
si está activo apaga POS, Ventas, Compras y Contabilidad. Los checks aplican para todos los usuarios, incluidos
administradores. El permiso del usuario "Administrar uso comercial de contactos" permite ver/editar el bloque y también ver contactos internos/sistema en la app Contactos.

Esta versión no ejecuta rutinas de actualización que reescriban contactos ni Empresas permitidas.
Además, Ajustes de Inventario queda limitado a ubicaciones internas sin sobreescribir métodos técnicos de búsqueda de stock.quant.

""",
    "author": "Alderete Informática",
    "website": "https://www.aldereteinformatica.com",
    "license": "LGPL-3",
    "depends": [
        "contacts",
        "sale",
        "purchase",
        "account",
        "stock",
        "point_of_sale",
    ],
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "data": [
        "security/ir_rule.xml",
        "views/res_partner_views.xml",
        "views/res_users_views.xml",
        "views/business_operation_views.xml",
        "data/auto_configure.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "assets": {
        "point_of_sale._assets_pos": [
            "multi_company_contacts/static/src/app/**/*.js",
        ],
    },
}
