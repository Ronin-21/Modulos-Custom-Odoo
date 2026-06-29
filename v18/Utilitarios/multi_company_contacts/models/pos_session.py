# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _mcc_with_skip_business_usage_validation(self):
        """Contexto técnico para que el cierre POS no se bloquee por partners internos.

        El filtro comercial de contactos sigue aplicando en el frontend POS y en
        las órdenes POS. Esto solo evita que los asientos/pagos internos del
        cierre de caja fallen cuando Odoo usa el partner de la compañía/sucursal.
        """
        return self.with_context(
            mcc_skip_business_usage_validation=True,
            mcc_skip_accounting_business_usage_validation=True,
        )

    def action_pos_session_closing_control(self, *args, **kwargs):
        return super(PosSession, self._mcc_with_skip_business_usage_validation()).action_pos_session_closing_control(*args, **kwargs)

    def action_pos_session_close(self, *args, **kwargs):
        return super(PosSession, self._mcc_with_skip_business_usage_validation()).action_pos_session_close(*args, **kwargs)

    def action_pos_session_validate(self, *args, **kwargs):
        return super(PosSession, self._mcc_with_skip_business_usage_validation()).action_pos_session_validate(*args, **kwargs)

    def _validate_session(self, *args, **kwargs):
        return super(PosSession, self._mcc_with_skip_business_usage_validation())._validate_session(*args, **kwargs)

    def _create_account_move(self, *args, **kwargs):
        return super(PosSession, self._mcc_with_skip_business_usage_validation())._create_account_move(*args, **kwargs)
