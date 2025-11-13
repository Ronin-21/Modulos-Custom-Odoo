{
    "name": "Control de Dependencias en Órdenes de Trabajo",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Abel Alejandro Acuña",
    "website": "https://ronin-webdesign.vercel.app/",
    "category": "Manufactura",
    "summary": "Controla las dependencias entre las operaciones de los centros de trabajo",
    "description": """
        Este módulo permite establecer y hacer cumplir dependencias entre las operaciones de trabajo
        dentro de una orden de fabricación. Las operaciones no podrán iniciarse hasta que se completen
        las operaciones previas de las cuales dependen.
    """,
    "depends": [
        "mrp_workorder",
    ],
    "data": [
        "views/mrp_bom_views.xml",
    ],
    'assets': {
    'web.assets_backend': [
        'shopfloor_order_blocked/static/src/js/workorder_error_handler.js',
        'shopfloor_order_blocked/static/src/css/blocked_error.css',
    ],
},
    "installable": True,
    "auto_install": False,
    "application": False,
}