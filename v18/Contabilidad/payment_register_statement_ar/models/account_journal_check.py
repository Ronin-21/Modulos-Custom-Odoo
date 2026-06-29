# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    prs_check_journal = fields.Boolean(
        string='Diario de cheques de terceros',
        default=False,
        help=(
            'Activar en diarios que actúan como cartera de cheques de terceros '
            '(ej: "Cheques de Terceros"). '
            'Cuando un cheque llega a este diario se considera "En cartera". '
            'Si llega a un diario de caja sin este flag, se considera "Cobrado en efectivo".'
        ),
    )
