# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    auc_enabled = fields.Boolean(
        string='Activar actualización automática de costos',
        default=False,
    )
    auc_moment = fields.Selection([
        ('confirm', 'Al confirmar la orden de compra'),
        ('receive', 'Al recibir la mercancía'),
        ('invoice', 'Al validar la factura de proveedor'),
    ], default='receive', string='Momento de actualización')

    auc_scope = fields.Selection([
        ('current', 'Solo en la compañía actual'),
        ('all', 'En todas las compañías (Multi-empresa)'),
    ], default='all', string='Alcance')

    auc_standard_strategy = fields.Selection([
        ('last', 'Último costo de compra'),
        ('avg_simple', 'Costo promedio (simple, sin stock)'),
    ], default='last', string='Estrategia Standard')

    auc_avco_replicate = fields.Boolean(
        string='AVCO: replicar promedio real a sucursales',
        default=True,
    )
    auc_propagate_manual_cost = fields.Boolean(
        string='Propagar cambios manuales de costo',
        default=False,
    )
    auc_propagate_manual_cost_include_avco = fields.Boolean(
        string='Incluir AVCO en propagación manual',
        default=False,
    )
    auc_recalc_bom = fields.Boolean(
        string='Recalcular BoM al cambiar costo',
        default=True,
    )

    def _auc_config(self):
        """
        Fuente única de configuración del módulo para esta compañía.
        Todos los modelos deben leer la config desde aquí, nunca desde ir.config_parameter.
        """
        self.ensure_one()
        return {
            'enabled':          self.auc_enabled,
            'moment':           self.auc_moment or 'receive',
            'scope':            self.auc_scope or 'all',
            'strategy':         self.auc_standard_strategy or 'last',
            'avco_replicate':   self.auc_avco_replicate,
            'recalc_bom':       self.auc_recalc_bom,
            'propagate_manual': self.auc_propagate_manual_cost,
            'propagate_avco':   self.auc_propagate_manual_cost_include_avco,
        }
