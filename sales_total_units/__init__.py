from . import models

#from odoo import api, SUPERUSER_ID

#def post_init_hook(cr, registry):
#    """Habilitar UOM y descuentos por línea en Ventas al instalar el módulo."""
#    env = api.Environment(cr, SUPERUSER_ID, {})

    # IDs técnicos de los grupos que queremos activar
#    groups_to_enable = [
#        'uom.group_uom',  # Unidades de medida
#        'sale.group_discount_per_so_line',  # Descuentos por línea de venta
#    ]

#    for group_xmlid in groups_to_enable:
#        try:
#            group = env.ref(group_xmlid, raise_if_not_found=False)
#            if group:
                # Asignar el grupo al usuario administrador (y con eso queda activo globalmente)
#                admin = env.ref('base.user_admin')
#                admin.groups_id = [(4, group.id)]
#                print(f"✓ Grupo habilitado: {group_xmlid}")
#            else:
#                print(f"✗ Grupo no encontrado: {group_xmlid}")
#       except Exception as e:
#            print(f"✗ Error activando {group_xmlid}: {e}")

#    print("✓ Post-init hook completado correctamente.")
