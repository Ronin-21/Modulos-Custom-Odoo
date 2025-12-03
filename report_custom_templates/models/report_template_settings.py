# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Vinculación con el modelo de configuración (NO usar related)
    report_template_config_id = fields.Many2one(
        'report.template.config',
        string='Configuración de Plantillas',
        compute='_compute_report_config',
        store=False,
        readonly=False
    )

    # ============================================================
    # DATOS GENERALES (campos directos, NO related)
    # ============================================================
    
    report_logo_text = fields.Char(
        string='Texto del Logo',
        help="Texto que aparece como logo en los reportes"
    )

    # ============================================================
    # COLORES (campos directos, NO related)
    # ============================================================
    
    report_primary_color = fields.Char(
        string='Color Primario',
        help="Color principal para headers y elementos destacados"
    )
    
    report_secondary_color = fields.Char(
        string='Color Secundario',
        help="Color para títulos y fondos secundarios"
    )
    
    report_header_bg_color = fields.Char(
        string='Fondo Header',
        help="Color de fondo para headers de información"
    )
    
    report_accent_color = fields.Char(
        string='Color de Acento',
        help="Color de acento para elementos secundarios"
    )

    # ============================================================
    # MRP (campos directos, NO related)
    # ============================================================
    
    report_enable_mrp = fields.Boolean(
        string='Activar Plantillas MRP',
        help="Activar plantillas personalizadas para MRP"
    )
    
    report_mrp_template = fields.Selection(
        [
            ('clean', 'Plantilla Limpia (con estilos)'),
            ('simple', 'Plantilla Simple (sin estilos)'),
            ('standard', 'Plantilla Estándar (Odoo por defecto)'),
        ],
        default='clean',
        string='Plantilla MRP',
        help="Selecciona el diseño para reportes de manufactura"
    )

    # ============================================================
    # VENTAS (campos directos, NO related)
    # ============================================================
    
    report_enable_sale = fields.Boolean(
        string='Activar Plantillas Ventas',
        help="Activar plantillas personalizadas para ventas"
    )
    
    report_sale_template = fields.Selection(
        [
            ('clean', 'Plantilla Limpia (con estilos)'),
            ('simple', 'Plantilla Simple (sin estilos)'),
            ('standard', 'Plantilla Estándar (Odoo por defecto)'),
        ],
        default='clean',
        string='Plantilla Ventas',
        help="Selecciona el diseño para reportes de ventas"
    )

    # ============================================================
    # COMPRAS (campos directos, NO related)
    # ============================================================
    
    report_enable_purchase = fields.Boolean(
        string='Activar Plantillas Compras',
        help="Activar plantillas personalizadas para compras"
    )
    
    report_purchase_template = fields.Selection(
        [
            ('clean', 'Plantilla Limpia (con estilos)'),
            ('simple', 'Plantilla Simple (sin estilos)'),
            ('standard', 'Plantilla Estándar (Odoo por defecto)'),
        ],
        default='clean',
        string='Plantilla Compras',
        help="Selecciona el diseño para reportes de compras"
    )

    # ============================================================
    # PAGOS (campos directos, NO related)
    # ============================================================
    
    report_enable_payment = fields.Boolean(
        string='Activar Plantillas Pagos',
        help="Activar plantillas personalizadas para pagos"
    )
    
    report_show_payment_checks = fields.Boolean(
        string='Mostrar Cheques',
        help="Mostrar tabla detallada de cheques en recibos"
    )

    @api.model
    def _compute_report_config(self):
        """Obtiene o crea la configuración para la empresa actual"""
        for settings in self:
            config = self.env['report.template.config'].search([
                ('company_id', '=', self.env.company.id),
                ('active', '=', True)
            ], limit=1)
            
            if not config:
                # Crear configuración si no existe
                config = self.env['report.template.config'].create({
                    'company_id': self.env.company.id,
                    'active': True
                })
            
            settings.report_template_config_id = config
    
    def get_values(self):
        """Cargar valores desde report.template.config"""
        res = super().get_values()
        
        config = self.env['report.template.config'].search([
            ('company_id', '=', self.env.company.id),
            ('active', '=', True)
        ], limit=1)
        
        if config:
            res.update({
                'report_logo_text': config.logo_text,
                'report_primary_color': config.primary_color,
                'report_secondary_color': config.secondary_color,
                'report_header_bg_color': config.header_bg_color,
                'report_accent_color': config.accent_color,
                'report_enable_mrp': config.enable_mrp_templates,
                'report_mrp_template': config.mrp_template,
                'report_enable_sale': config.enable_sale_templates,
                'report_sale_template': config.sale_template,
                'report_enable_purchase': config.enable_purchase_templates,
                'report_purchase_template': config.purchase_template,
                'report_enable_payment': config.enable_payment_templates,
                'report_show_payment_checks': config.show_payment_checks,
            })
        
        return res
    
    def set_values(self):
        """Guardar valores en report.template.config"""
        super().set_values()
        
        # Obtener o crear la configuración
        config = self.env['report.template.config'].search([
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        if not config:
            config = self.env['report.template.config'].create({
                'company_id': self.env.company.id,
                'active': True
            })
        
        # Actualizar todos los campos
        config.write({
            'logo_text': self.report_logo_text,
            'primary_color': self.report_primary_color,
            'secondary_color': self.report_secondary_color,
            'header_bg_color': self.report_header_bg_color,
            'accent_color': self.report_accent_color,
            'enable_mrp_templates': self.report_enable_mrp,
            'mrp_template': self.report_mrp_template,
            'enable_sale_templates': self.report_enable_sale,
            'sale_template': self.report_sale_template,
            'enable_purchase_templates': self.report_enable_purchase,
            'purchase_template': self.report_purchase_template,
            'enable_payment_templates': self.report_enable_payment,
            'show_payment_checks': self.report_show_payment_checks,
        })