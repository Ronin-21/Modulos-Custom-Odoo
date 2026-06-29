# -*- coding: utf-8 -*-
from odoo import models, fields, api

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    prs_statement_id = fields.Many2one(
        'account.bank.statement',
        string="Asignar en Estado de Cuenta",
        help="Si se selecciona, el extracto creado por este pago se asignará a este Estado de Cuenta (solo abiertos).",
    )

    @api.onchange('journal_id')
    def _onchange_journal_id_prs_statement(self):
        for wizard in self:
            wizard.prs_statement_id = False
            if not wizard.journal_id:
                continue
            # Default: último estado de cuenta ABIERTO del diario
            Statement = wizard.env['account.bank.statement']
            domain = [('journal_id', '=', wizard.journal_id.id)]
            if 'prs_state' in Statement._fields:
                domain.append(('prs_state', '=', 'open'))
            stmt = Statement.search(domain, order='date desc, id desc', limit=1)
            wizard.prs_statement_id = stmt

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
    
        # Pasar asignación a Estado de Cuenta (si el usuario lo eligió)
        if self.prs_statement_id and self.env.user.has_group(
            'payment_register_statement.group_prs_assign_payments_to_statements'
        ):
            vals['prs_statement_id'] = self.prs_statement_id.id
    
        # Si se registra pago desde facturas de proveedor, heredar concepto si es único
        concept_id = False
        try:
            lines = getattr(self, 'line_ids', False)
            moves = lines.move_id if lines else self.env['account.move']
            concepts = moves.mapped('prs_expense_concept_id').filtered(lambda c: c)
            if len(concepts) == 1:
                concept_id = concepts.id
        except Exception:
            concept_id = False
    
        if concept_id and 'prs_expense_concept_id' in self.env['account.payment']._fields:
            vals['prs_expense_concept_id'] = concept_id
    
        return vals
