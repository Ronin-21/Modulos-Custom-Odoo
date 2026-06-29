# -*- coding: utf-8 -*-
from odoo import fields, models


class PrsCardProvider(models.Model):
    _name = 'prs.card.provider'
    _description = 'Procesador de tarjetas (Payway, Clover, Mercado Pago Point, etc.)'
    _order = 'sequence, name'
    _check_company_auto = True

    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(
        string='Codigo',
        help='Identificador tecnico para integraciones futuras (ej: payway, clover, mercadopago).',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Contacto',
        ondelete='set null',
        help='Proveedor asociado a este procesador. Se usa como partner en las líneas de extracto '
             'de acreditación y en el asiento de comisión, para identificar movimientos '
             'por procesador.',
    )
    card_ids = fields.One2many('account.card', 'provider_id', string='Tarjetas')
    card_count = fields.Integer(string='Tarjetas', compute='_compute_card_count')
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='company_id.currency_id',
        readonly=True,
    )

    # Acreditacion por defecto — las tarjetas heredan si no tienen valor propio
    settlement_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de acreditacion',
        domain="[('type', '=', 'bank')]",
        check_company=True,
        help='Cuenta bancaria donde este procesador deposita las liquidaciones. '
             'Las tarjetas pueden sobreescribir este valor.',
    )
    settlement_delay_days = fields.Integer(
        string='Dias de acreditacion',
        default=0,
        help='Dias que tarda el procesador en liquidar. Valor por defecto para sus tarjetas.',
    )
    settlement_day_type = fields.Selection(
        [('calendar', 'Dias corridos'), ('business', 'Dias habiles')],
        string='Tipo de dias',
        default='calendar',
    )

    # Comisiones por defecto — las tarjetas heredan si no tienen valor propio
    fee_percent = fields.Float(string='Comision (%)', default=0.0)
    fee_fixed_amount = fields.Monetary(string='Comision fija', currency_field='currency_id', default=0.0)
    fee_tax_percent = fields.Float(string='IVA comision (%)', default=0.0)
    withholding_percent = fields.Float(string='Retencion/Percepcion (%)', default=0.0)

    def _compute_card_count(self):
        for provider in self:
            provider.card_count = len(provider.card_ids)

    def action_open_cards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tarjetas — %s' % self.name,
            'res_model': 'account.card',
            'view_mode': 'list,form',
            'domain': [('provider_id', '=', self.id)],
            'context': {'default_provider_id': self.id},
        }

    def action_open_assign_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asignar tarjetas a %s' % self.name,
            'res_model': 'prs.card.assign.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_provider_id': self.id},
        }
