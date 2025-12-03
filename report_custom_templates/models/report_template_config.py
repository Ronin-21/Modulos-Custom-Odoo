# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ReportTemplateConfig(models.Model):
    _name = 'report.template.config'
    _description = 'Configuración de Plantillas de Reportes'
    _rec_name = 'company_id'

    # Empresa
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        ondelete='cascade',
        help='Empresa a la que aplica esta configuración'
    )

    # ============================================================
    # DATOS GENERALES
    # ============================================================
    
    logo_text = fields.Char(
        "Texto del Logo",
        default="PM",
        help="Texto que aparece como logo en los reportes (ej: PM, EMPRESA, etc.)"
    )
    
    # ============================================================
    # CONFIGURACIÓN DE COLORES
    # ============================================================
    
    primary_color = fields.Char(
        "Color Primario",
        default="#FF6B00",
        help="Color principal para headers y elementos destacados (formato hex)"
    )
    
    secondary_color = fields.Char(
        "Color Secundario",
        default="#2C3E50",
        help="Color para títulos y fondos secundarios (formato hex)"
    )
    
    header_bg_color = fields.Char(
        "Color Fondo Header",
        default="#ECF0F1",
        help="Color de fondo para headers de información (formato hex)"
    )
    
    accent_color = fields.Char(
        "Color de Acento",
        default="#E8F5E9",
        help="Color de acento para elementos secundarios (formato hex)"
    )
    
    # ============================================================
    # OPCIONES POR MÓDULO - MRP
    # ============================================================
    
    enable_mrp_templates = fields.Boolean(
        "Activar plantillas MRP",
        default=True,
        help="Habilitar plantillas personalizadas para órdenes de manufactura"
    )
    
    mrp_template = fields.Selection(
        [
            ('clean', 'Plantilla Limpia (con estilos)'),
            ('simple', 'Plantilla Simple (sin estilos)'),
            ('standard', 'Plantilla Estándar (Odoo por defecto)'),
        ],
        default='clean',
        string="Plantilla MRP",
        help="Selecciona el diseño para reportes de MRP"
    )
    
    # ============================================================
    # OPCIONES POR MÓDULO - VENTAS
    # ============================================================
    
    enable_sale_templates = fields.Boolean(
        "Activar plantillas Ventas",
        default=True,
        help="Habilitar plantillas personalizadas para órdenes de venta"
    )
    
    sale_template = fields.Selection(
        [
            ('clean', 'Plantilla Limpia (con estilos)'),
            ('simple', 'Plantilla Simple (sin estilos)'),
            ('standard', 'Plantilla Estándar (Odoo por defecto)'),
        ],
        default='clean',
        string="Plantilla Ventas",
        help="Selecciona el diseño para reportes de ventas"
    )
    
    # ============================================================
    # OPCIONES POR MÓDULO - COMPRAS
    # ============================================================
    
    enable_purchase_templates = fields.Boolean(
        "Activar plantillas Compras",
        default=True,
        help="Habilitar plantillas personalizadas para órdenes de compra"
    )
    
    purchase_template = fields.Selection(
        [
            ('clean', 'Plantilla Limpia (con estilos)'),
            ('simple', 'Plantilla Simple (sin estilos)'),
            ('standard', 'Plantilla Estándar (Odoo por defecto)'),
        ],
        default='clean',
        string="Plantilla Compras",
        help="Selecciona el diseño para reportes de compras"
    )
    
    # ============================================================
    # OPCIONES POR MÓDULO - CONTABILIDAD
    # ============================================================
    
    enable_payment_templates = fields.Boolean(
        "Activar plantillas de Pagos",
        default=True,
        help="Habilitar plantillas personalizadas para recibos de pago"
    )
    
    show_payment_checks = fields.Boolean(
        "Mostrar cheques en recibos",
        default=True,
        help="Mostrar tabla detallada de cheques en recibos de pago"
    )
    
    # ============================================================
    # CAMPOS TÉCNICOS
    # ============================================================
    
    active = fields.Boolean(
        "Activo",
        default=True,
        help="Desactiva esta configuración sin eliminarla"
    )
    
    _sql_constraints = [
        ('unique_company', 'unique(company_id)', 'Ya existe configuración para esta empresa'),
    ]
    
    def write(self, vals):
        """Override write para asegurar guardado correcto"""
        result = super().write(vals)
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create para asegurar creación correcta"""
        records = super().create(vals_list)
        return records
    
    @api.model
    def get_config(self, company_id=None):
        """
        Obtiene la configuración para una empresa específica.
        Si no la encuentra, retorna la configuración por defecto.
        """
        if not company_id:
            company_id = self.env.company.id
        
        config = self.search([
            ('company_id', '=', company_id),
            ('active', '=', True)
        ], limit=1)
        
        return config if config else self.env['report.template.config']
    
    def get_template_path(self, module_name):
        """
        Retorna la plantilla a usar para un módulo específico.
        
        Args:
            module_name: 'mrp', 'sale', 'purchase', 'payment'
        
        Returns:
            str: Ruta de la plantilla (ej: 'report_custom_templates.report_mrporder_clean')
        """
        template_field = f'{module_name}_template'
        
        if not hasattr(self, template_field):
            return None
        
        template_type = getattr(self, template_field)
        
        # Mapear módulos a nombres de plantillas
        module_mapping = {
            'mrp': f'report_mrporder_{template_type}',
            'sale': f'report_saleorder_{template_type}',
            'purchase': f'report_purchaseorder_{template_type}',
            'payment': f'report_payment_receipt_{template_type}',
        }
        
        template_name = module_mapping.get(module_name)
        if template_name:
            return f'report_custom_templates.{template_name}'
        
        return None