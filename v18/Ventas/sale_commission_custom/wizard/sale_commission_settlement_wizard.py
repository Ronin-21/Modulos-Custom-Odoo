# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleCommissionSettlementWizard(models.TransientModel):
    _name = 'sale.commission.settlement.wizard'
    _description = 'Asistente de Liquidación de Comisiones'

    salesperson_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        required=True,
        domain=[('share', '=', False)],
    )
    date_from = fields.Date(
        string='Desde',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Hasta',
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
    )
    preview_count = fields.Integer(
        string='Comisiones a liquidar',
        compute='_compute_preview',
    )
    preview_amount = fields.Float(
        string='Total a liquidar',
        compute='_compute_preview',
        digits=(16, 2),
    )

    @api.depends('salesperson_id', 'date_from', 'date_to', 'company_id')
    def _compute_preview(self):
        for wiz in self:
            if not (wiz.salesperson_id and wiz.date_from and wiz.date_to):
                wiz.preview_count = 0
                wiz.preview_amount = 0.0
                continue

            config = self.env['sale.commission.config'].get_config(wiz.company_id)
            start_date = config.commission_start_date

            domain = [
                ('salesperson_id', '=', wiz.salesperson_id.id),
                ('state', '=', 'earned'),
                ('settlement_id', '=', False),
                ('payment_date', '>=', wiz.date_from),
                ('payment_date', '<=', wiz.date_to),
                ('company_id', '=', wiz.company_id.id),
            ]
            # FIX: Se sincronizó el domain del preview con el de action_load_commissions.
            # Antes el preview no aplicaba commission_start_date y mostraba un
            # conteo mayor al que realmente se cargaba en la liquidación.
            if start_date:
                domain.append(('payment_date', '>=', start_date))

            lines = self.env['sale.commission.line'].search(domain)
            wiz.preview_count = len(lines)
            wiz.preview_amount = sum(lines.mapped('commission_amount'))

    def action_create_settlement(self):
        self.ensure_one()
        if self.preview_count == 0:
            raise UserError(
                'No existen comisiones ganadas para los criterios '
                'seleccionados.')
        settlement = self.env['sale.commission.settlement'].create({
            'salesperson_id': self.salesperson_id.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
        })
        settlement.action_load_commissions()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Liquidación creada',
            'res_model': 'sale.commission.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
        }
