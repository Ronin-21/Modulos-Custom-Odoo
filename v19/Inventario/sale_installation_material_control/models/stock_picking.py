# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError

INSTALLATION_MOVE_TYPE_SELECTION = [
    ('reserve', 'Reserva'),
    ('withdraw', 'Retiro'),
    ('return', 'Devolución'),
    ('consume', 'Consumo'),
    ('release', 'Liberación'),
]


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    installation_id = fields.Many2one(
        'sale.installation.material', string='Control de Instalación', copy=False, index=True)
    installation_move_type = fields.Selection(
        INSTALLATION_MOVE_TYPE_SELECTION, string='Movimiento de instalación', copy=False)
    installation_responsible_id = fields.Many2one(
        'res.users', string='Responsable / Instalador', copy=False)
    installation_sale_order_id = fields.Many2one(
        related='installation_id.sale_order_id', string='Venta (instalación)', store=False)
    installation_project_id = fields.Many2one(
        related='installation_id.project_id', string='Proyecto (instalación)', store=False)

    def action_open_installation_withdrawal(self):
        self.ensure_one()
        if not self.installation_id:
            raise UserError(_('Esta entrega no está vinculada a un control de instalación.'))
        return self.installation_id.action_open_withdrawal_wizard()

    def action_open_installation_return(self):
        self.ensure_one()
        if not self.installation_id:
            raise UserError(_('Esta entrega no está vinculada a un control de instalación.'))
        return self.installation_id.action_open_return_wizard()

    def action_view_installation_control(self):
        self.ensure_one()
        if not self.installation_id:
            raise UserError(_('Esta entrega no está vinculada a un control de instalación.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.installation.material',
            'res_id': self.installation_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
