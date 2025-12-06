# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Enlace (no related) a la configuración persistente
    report_template_config_id = fields.Many2one(
        "report.template.config",
        string="Configuración de Plantillas",
        compute="_compute_report_config",
        store=False,
        readonly=False,
    )

    # ============================================================
    # DATOS GENERALES
    # ============================================================

    report_logo_text = fields.Char(
        string="Texto del Logo",
        help="Texto corto para usar como logo en la cabecera de los reportes.",
    )

    report_primary_color = fields.Char(
        string="Color Primario",
        help="Color principal para encabezados y elementos destacados.",
    )
    report_secondary_color = fields.Char(
        string="Color Secundario",
        help="Color secundario para títulos.",
    )
    report_header_bg_color = fields.Char(
        string="Fondo Header",
        help="Color de fondo de cuadros de información.",
    )
    report_accent_color = fields.Char(
        string="Color de Acento",
        help="Color de acento para detalles.",
    )

    # ============================================================
    # MRP
    # ============================================================

    report_enable_mrp = fields.Boolean(
        string="Activar Plantillas MRP",
        help="Activar plantillas personalizadas para manufactura.",
    )
    report_mrp_template = fields.Selection(
        [
            ("clean", "Plantilla Limpia (con estilos)"),
            ("simple", "Plantilla Simple (sin estilos)"),
            ("standard", "Plantilla Estándar (Odoo por defecto)"),
        ],
        default="clean",
        string="Plantilla MRP",
        help="Selecciona el diseño para reportes de manufactura.",
    )

    # ============================================================
    # VENTAS
    # ============================================================

    report_enable_sale = fields.Boolean(
        string="Activar Plantillas Ventas",
        help="Activar cabecera personalizada para cotizaciones y pedidos.",
    )
    report_sale_logo_mode = fields.Selection(
        [
            ("image", "Logo de la empresa (imagen)"),
            ("text", "Logo definido por texto"),
        ],
        default="text",
        string="Modo de cabecera en Ventas",
        help="Elegí si las cotizaciones usan el logo de imagen o el texto configurado.",
    )

    # ============================================================
    # COMPRAS
    # ============================================================

    report_enable_purchase = fields.Boolean(
        string="Activar Plantillas Compras",
        help="Activar plantillas personalizadas para órdenes de compra.",
    )
    report_purchase_template = fields.Selection(
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
    # PAGOS
    # ============================================================

    report_enable_payment = fields.Boolean(
        string="Activar Plantillas Pagos",
        help="Activar plantillas personalizadas para recibos de pago.",
    )
    report_show_payment_checks = fields.Boolean(
        string="Mostrar Cheques",
        help="Mostrar tabla detallada de cheques en recibos.",
    )

    # ============================================================
    # LÓGICA DE LECTURA / ESCRITURA
    # ============================================================

    @api.depends("company_id")
    def _compute_report_config(self):
        for settings in self:
            config = self.env["report.template.config"].search(
                [
                    ("company_id", "=", settings.company_id.id or self.env.company.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if not config:
                config = self.env["report.template.config"].create(
                    {
                        "company_id": settings.company_id.id or self.env.company.id,
                        "active": True,
                    }
                )
            settings.report_template_config_id = config

    def get_values(self):
        res = super().get_values()
        config = self.env["report.template.config"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("active", "=", True),
            ],
            limit=1,
        )
        if config:
            res.update(
                {
                    "report_logo_text": config.logo_text,
                    "report_primary_color": config.primary_color,
                    "report_secondary_color": config.secondary_color,
                    "report_header_bg_color": config.header_bg_color,
                    "report_accent_color": config.accent_color,
                    "report_enable_mrp": config.enable_mrp_templates,
                    "report_mrp_template": config.mrp_template,
                    "report_enable_sale": config.enable_sale_templates,
                    "report_sale_logo_mode": config.sale_logo_mode,
                    "report_enable_purchase": config.enable_purchase_templates,
                    "report_purchase_template": config.purchase_template,
                    "report_enable_payment": config.enable_payment_templates,
                    "report_show_payment_checks": config.show_payment_checks,
                }
            )
        return res

    def set_values(self):
        super().set_values()
        config = self.env["report.template.config"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        if not config:
            config = self.env["report.template.config"].create(
                {"company_id": self.env.company.id, "active": True}
            )

        config.write(
            {
                "logo_text": self.report_logo_text,
                "primary_color": self.report_primary_color,
                "secondary_color": self.report_secondary_color,
                "header_bg_color": self.report_header_bg_color,
                "accent_color": self.report_accent_color,
                "enable_mrp_templates": self.report_enable_mrp,
                "mrp_template": self.report_mrp_template,
                "enable_sale_templates": self.report_enable_sale,
                "sale_logo_mode": self.report_sale_logo_mode,
                "enable_purchase_templates": self.report_enable_purchase,
                "purchase_template": self.report_purchase_template,
                "enable_payment_templates": self.report_enable_payment,
                "show_payment_checks": self.report_show_payment_checks,
            }
        )
