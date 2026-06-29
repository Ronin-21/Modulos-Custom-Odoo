# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    prs_expense_concept_id = fields.Many2one(
        'prs.expense.concept',
        string="Concepto de gasto",
        help="Clasificación de gastos (Concepto/Subconcepto).",
        index=True,
    )

    @api.onchange('partner_id')
    def _onchange_partner_id_prs_expense_concept(self):
        for move in self:
            if move.partner_id and not move.prs_expense_concept_id and move.partner_id.prs_expense_concept_id:
                move.prs_expense_concept_id = move.partner_id.prs_expense_concept_id

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move, vals in zip(moves, vals_list):
            if not vals.get('prs_expense_concept_id') and move.partner_id and move.partner_id.prs_expense_concept_id:
                # solo aplicar por defecto en facturas/NC/recibos de proveedor
                if move.move_type in ('in_invoice', 'in_refund', 'in_receipt'):
                    move.prs_expense_concept_id = move.partner_id.prs_expense_concept_id
        return moves


class AccountMoveMultiCompanyValidation(models.Model):
    """Validación de acceso multiempresa para diarios de tipo EFECTIVO.

    Separado de AccountPayment para no mezclar responsabilidades.
    El módulo PRS permite que un diario de caja sea compartido entre empresas
    (campo allowed_company_ids). Este modelo asegura que los asientos manuales
    también respeten esa restricción.
    """
    _inherit = 'account.move'

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            for line in move.line_ids:
                j = line.journal_id
                if (
                    j
                    and j.type == 'cash'
                    and move.company_id != j.company_id
                    and move.company_id not in getattr(j, 'allowed_company_ids', self.env['res.company'])
                ):
                    raise ValidationError(
                        "El diario %s no está permitido para la empresa %s."
                        % (j.name, move.company_id.display_name)
                    )
        return moves

    # action_post NO se sobreescribe aquí.
    #
    # La creación de extractos bancarios automáticos es responsabilidad
    # exclusiva de AccountPayment.action_post() para pagos, y del wizard
    # PrsInternalTransferWizard para transferencias internas.
    #
    # Sobreescribir action_post en AccountMove causaba duplicación de
    # extractos porque Odoo llama action_post() internamente cada vez que
    # crea o modifica una account.bank.statement.line (hereda de account.move
    # via _inherits).
