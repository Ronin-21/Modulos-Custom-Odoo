from odoo import http
from odoo.http import request
import base64


class PosBrandingController(http.Controller):
    """Controlador para recursos dinámicos de branding del POS."""

    @http.route('/pos/branding/logo/<int:config_id>', type='http', auth='user')
    def get_pos_logo(self, config_id, **kwargs):
        """Devuelve el logo personalizado como imagen binaria.

        Se devuelve sin caché para que al cambiar el logo en la configuración
        se vea el nuevo inmediatamente al abrir una nueva sesión de POS.
        """
        config = request.env['pos.config'].browse(config_id)
        if config and config.custom_logo:
            return request.make_response(
                base64.b64decode(config.custom_logo),
                headers=[
                    ('Content-Type', 'image/png'),
                    ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'),
                ],
            )
        return request.not_found()

    @http.route('/pos/branding/background/<int:config_id>', type='http', auth='user')
    def get_pos_background(self, config_id, **kwargs):
        """Devuelve la imagen de fondo personalizada del POS."""
        config = request.env['pos.config'].browse(config_id)
        if config and config.custom_background:
            return request.make_response(
                base64.b64decode(config.custom_background),
                headers=[
                    ('Content-Type', 'image/jpeg'),
                    ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'),
                ],
            )
        return request.not_found()

    @http.route('/pos/branding/css/<int:config_id>', type='http', auth='user')
    def get_pos_custom_css(self, config_id, **kwargs):
        """Genera SOLO variables CSS para el POS según la configuración.

        El diseño (bordes, tamaños, etc.) se controla desde pos_custom_styles.css
        usando estas variables.

        Variables definidas en .pos:

          --pos-primary-color       Color primario
          --pos-secondary-color     Color secundario
          --pos-accent-color        Color de acento
          --pos-logo-url            url(...) del logo
          --pos-background-image    url(...) del fondo
        """
        config = request.env['pos.config'].browse(config_id)

        # Valores por defecto si algo está vacío
        primary = config.primary_color or '#ffc107'
        secondary = config.secondary_color or '#ff9800'
        accent = config.accent_color or '#f57c00'

        logo_url = f"url('/pos/branding/logo/{config_id}')" if config.custom_logo else 'none'
        bg_url = f"url('/pos/branding/background/{config_id}')" if config.custom_background else 'none'

        css = f"""
        /* Variables dinámicas para POS config {config_id} */
        .pos {{
            --pos-primary-color: {primary};
            --pos-secondary-color: {secondary};
            --pos-accent-color: {accent};
            --pos-logo-url: {logo_url};
            --pos-background-image: {bg_url};
        }}
        """

        return request.make_response(
            css,
            headers=[
                ('Content-Type', 'text/css'),
                ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'),
            ],
        )
