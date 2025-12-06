# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ReportTemplateConfig(models.Model):
    _name = "report.template.config"
    _description = "Configuración de Plantillas de Reportes"
    _rec_name = "company_id"

    # Empresa a la que aplica esta configuración
    company_id = fields.Many2one(
        "res.company",
        string="Empresa",
        required=True,
        ondelete="cascade",
        help="Empresa a la que aplica esta configuración",
    )

    # ============================================================
    # DATOS GENERALES
    # ============================================================

    logo_text = fields.Char(
        "Texto del Logo",
        default="AI",
        help="Texto que aparece como logo en los reportes (ej: sigla de la empresa).",
    )

    # ============================================================
    # COLORES
    # ============================================================

    primary_color = fields.Char(
        "Color Primario",
        default="#FF6B55",
        help="Color principal para encabezados y elementos destacados (formato HEX).",
    )
    secondary_color = fields.Char(
        "Color Secundario",
        default="#ECF0F1",
        help="Color secundario para títulos (formato HEX).",
    )
    header_bg_color = fields.Char(
        "Fondo Header",
        default="#E8F5E9",
        help="Color de fondo de cuadros de información (formato HEX).",
    )
    accent_color = fields.Char(
        "Color de Acento",
        default="#FF6B00",
        help="Color de acento para pequeños detalles (formato HEX).",
    )

    # ============================================================
    # MRP
    # ============================================================

    enable_mrp_templates = fields.Boolean(
        "Activar plantillas MRP",
        default=False,
        help="Habilitar plantillas personalizadas para órdenes de manufactura.",
    )
    mrp_template = fields.Selection(
        [
            ("clean", "Plantilla Limpia (con estilos)"),
            ("simple", "Plantilla Simple (sin estilos)"),
            ("standard", "Plantilla Estándar (Odoo por defecto)"),
        ],
        default="clean",
        string="Plantilla MRP",
        help="Selecciona el diseño para reportes de MRP.",
    )

    # ============================================================
    # VENTAS / COTIZACIONES
    # ============================================================

    enable_sale_templates = fields.Boolean(
        "Activar cabecera personalizada en Ventas",
        default=True,
        help="Si está activo, las cotizaciones/pedidos pueden usar cabecera con logo de texto.",
    )
    sale_logo_mode = fields.Selection(
        [
            ("image", "Logo de la empresa (imagen)"),
            ("text", "Logo definido por texto"),
        ],
        default="text",
        string="Modo de cabecera en ventas",
        help="Elegí si la cabecera usa el logo de imagen de la empresa o el texto configurado.",
    )

    # ============================================================
    # COMPRAS
    # ============================================================

    enable_purchase_templates = fields.Boolean(
        "Activar plantillas Compras",
        default=False,
        help="Habilitar plantillas personalizadas para órdenes de compra.",
    )
    purchase_template = fields.Selection(
        [
            ("clean", "Plantilla Limpia (con estilos)"),
            ("simple", "Plantilla Simple (sin estilos)"),
            ("standard", "Plantilla Estándar (Odoo por defecto)"),
        ],
        default="clean",
        string="Plantilla Compras",
        help="Selecciona el diseño para reportes de compras.",
    )

    # ============================================================
    # PAGOS / RECIBOS
    # ============================================================

    enable_payment_templates = fields.Boolean(
        "Activar plantillas de Pagos",
        default=True,
        help="Habilitar plantillas personalizadas para recibos de pago.",
    )
    show_payment_checks = fields.Boolean(
        "Mostrar cheques en recibos",
        default=True,
        help="Si está activo, los recibos mostrarán una tabla con los cheques utilizados.",
    )

    # ============================================================
    # CAMPOS TÉCNICOS
    # ============================================================

    active = fields.Boolean(
        "Activo",
        default=True,
        help="Desactiva esta configuración sin eliminarla.",
    )

    _sql_constraints = [
        (
            "unique_company",
            "unique(company_id)",
            "Ya existe una configuración de plantillas para esta empresa.",
        )
    ]

    def write(self, vals):
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)

    # Utilidad para obtener la config de la empresa
    @api.model
    def get_config(self, company_id=None):
        if not company_id:
            company_id = self.env.company.id
        config = self.search(
            [("company_id", "=", company_id), ("active", "=", True)], limit=1
        )
        return config or self.env["report.template.config"]

    # Utilidad opcional para MRP / Compras / Pagos
    def get_template_path(self, module_name):
        """Retorna la plantilla a usar para un módulo específico.

        Hoy se usa solo para MRP / Compras / Pagos.
        """
        template_field = f"{module_name}_template"
        if not hasattr(self, template_field):
            return None

        template_type = getattr(self, template_field)
        module_mapping = {
            "mrp": f"report_mrporder_{template_type}",
            "purchase": f"report_purchaseorder_{template_type}",
            "payment": f"report_payment_receipt_{template_type}",
        }
        template_name = module_mapping.get(module_name)
        return f"report_custom_templates.{template_name}" if template_name else None
