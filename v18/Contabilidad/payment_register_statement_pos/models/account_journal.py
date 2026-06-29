# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    prs_pos_deposit_require_validation = fields.Boolean(
        string="Requerir validación en depósitos POS",
        default=False,
        help=(
            "Aplica cuando este diario es el DESTINO de un depósito de caja POS "
            "(pos_cash_transfer).\n\n"
            "Si está ACTIVO: el depósito solo genera el extracto negativo en la "
            "Caja POS origen. El extracto positivo en este diario NO se crea "
            "automáticamente — el administrador lo valida manualmente desde el "
            "tablero de conciliación bancaria.\n\n"
            "Si está DESACTIVADO (default): comportamiento estándar — se crean "
            "los dos extractos automáticamente al confirmar el depósito."
        ),
    )
