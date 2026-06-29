from odoo import models, fields, api

class PosConfig(models.Model):
    _inherit = 'pos.config'
    
    # Configuración de colores
    primary_color = fields.Char(
        string='Color Primario',
        default='#FFC107',
        help='Color principal del POS (navbar, botones)'
    )
    secondary_color = fields.Char(
        string='Color Secundario',
        default='#FF9800',
        help='Color secundario (hover, bordes)'
    )
    accent_color = fields.Char(
        string='Color de Acento',
        default='#F57C00',
        help='Color de elementos activos'
    )
    
    # Logo personalizado
    custom_logo = fields.Binary(
        string='Logo Personalizado',
        help='Logo que se mostrará en el navbar del POS'
    )
    custom_logo_filename = fields.Char(string='Nombre del Logo')
    
    # Fondo personalizado
    custom_background = fields.Binary(
        string='Imagen de Fondo',
        help='Imagen de fondo para el POS'
    )
    custom_background_filename = fields.Char(string='Nombre del Fondo')
    
    use_custom_branding = fields.Boolean(
        string='Usar Personalización',
        default=False,
        help='Activar personalización de colores y logo'
    )
    
    # Texto alternativo si no hay logo
    branding_text = fields.Char(
        string='Texto del Navbar',
        help='Texto a mostrar si no hay logo (ej: nombre de la sucursal)'
    )