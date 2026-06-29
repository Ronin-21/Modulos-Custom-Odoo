# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleCommissionConfig(models.Model):
    _name = 'sale.commission.config'
    _description = 'Configuración de Comisiones'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
    )
    active = fields.Boolean(
        string='Módulo activo',
        default=True,
        help='Desactivar para suspender el cómputo de comisiones en esta compañía.',
    )
    default_commission_percent = fields.Float(
        string='Porcentaje de comisión por defecto (%)',
        digits=(5, 2),
        default=5.0,
    )

    commission_start_date = fields.Date(
        string='Fecha inicio de comisiones',
        required=True,
        default=fields.Date.today,
        help='No se generarán comisiones para facturas pagadas antes de esta fecha.',
    )

    expense_account_id = fields.Many2one(
        'account.account',
        string='Cuenta gasto comisión',
        help='Cuenta de gasto o cuenta destino del pago, por ejemplo SUELDOS.',
    )

    payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de pago por defecto',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='Diario por defecto desde donde saldrá el pago de la comisión.',
    )

    commission_base = fields.Selection([
        ('amount_untaxed', 'Subtotal sin impuestos'),
        ('amount_total', 'Total con impuestos'),
    ], string='Base de comisión', default='amount_untaxed', required=True)

    partial_payment_mode = fields.Selection([
        ('full_only', 'Solo al pago total de la factura'),
        ('proportional', 'Proporcional al cobro parcial'),
    ], string='Modo de pago parcial', default='full_only', required=True)

    credit_note_behavior = fields.Selection([
        ('auto_deduct', 'Descontar comisión automáticamente'),
        ('block', 'Bloquear comisión hasta resolver'),
        ('negative_adjustment', 'Generar ajuste negativo'),
    ], string='Comportamiento con notas de crédito',
        default='auto_deduct', required=True)

    rounding = fields.Selection([
        ('no', 'Sin redondeo'),
        ('1', 'Al entero más cercano'),
        ('0.01', 'A 2 decimales'),
    ], string='Redondeo de comisión', default='0.01')

    _sql_constraints = [
        ('unique_company', 'UNIQUE(company_id)',
         'Solo puede existir una configuración de comisiones por compañía.'),
    ]

    @api.constrains('default_commission_percent')
    def _check_percent(self):
        for rec in self:
            if rec.default_commission_percent < 0 or rec.default_commission_percent > 100:
                raise ValidationError(
                    'El porcentaje de comisión debe estar entre 0 y 100.'
                )

    @api.model
    def get_config(self, company=None):
        company = company or self.env.company
        config = self.search([('company_id', '=', company.id)], limit=1)
        if not config:
            config = self.create({
                'company_id': company.id,
                'commission_start_date': fields.Date.today(),
            })
        return config