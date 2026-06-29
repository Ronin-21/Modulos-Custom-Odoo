# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    """
    Extensión de account.payment para, después de postear el pago,
    poder crear asientos espejo entre sucursales (lógica a afinar).

    IMPORTANTE:
    - NO define campos nuevos en res.company.
    - NO rompe la lógica ya existente en account_payment.py: action_post()
      se ejecuta primero allí (auto extractos, validaciones, etc.) y luego
      se llama a _create_interbranch_counterpart_moves().
    """
    _inherit = "account.payment"

    def action_post(self):
        # Ejecuta toda la lógica ya definida en otros _inherit
        res = super().action_post()
        # Luego permite crear el asiento espejo (si corresponde)
        self._create_interbranch_counterpart_moves()
        return res

    # ------------------------------------------------------------------
    # Lógica de contrapartida entre sucursales (INICIAL / A AFINAR)
    # ------------------------------------------------------------------

    def _create_interbranch_counterpart_moves(self):
        """GANCHO: para transferencias internas entre diarios de compañías
        distintas pero con la misma empresa matriz, podemos crear un asiento
        espejo en la compañía destino.

        Ahora mismo sólo está la estructura básica; la condición concreta de
        cuándo dispararlo la afinaremos una vez que veamos qué pagos usás
        realmente para las transferencias de liquidez.
        """
        Move = self.env["account.move"]

        for payment in self:
            # Evitar recursión si nosotros mismos creamos el asiento
            if self.env.context.get("no_interbranch_counterpart"):
                continue

            # 🔹 Por ahora salimos directamente: dejamos el gancho listo
            #    para no cambiar ningún comportamiento mientras probamos.
            #    Más adelante, cuando tengamos claro el flujo exacto
            #    (is_internal_transfer, diarios, etc.), pondremos aquí
            #    la condición real y la creación del asiento espejo.
            continue

            # -- EJEMPLO de estructura (comentado):
            #
            # dest_journal = getattr(payment, "destination_journal_id", False)
            # if not dest_journal:
            #     continue
            #
            # company_from = payment.company_id
            # company_to = dest_journal.company_id
            #
            # if company_from == company_to:
            #     continue
            #
            # parent_from = company_from.parent_id or company_from
            # parent_to = company_to.parent_id or company_to
            # if parent_from != parent_to:
            #     continue
            #
            # # Cuenta puente estándar en la compañía destino
            # bridge_account = company_to.transfer_account_id
            # if not bridge_account:
            #     _logger.info(
            #         "Pago %s: no se crea asiento inter-sucursal porque la "
            #         "compañía %s no tiene configurada la 'Cuenta de transferencia'.",
            #         payment.name or payment.id,
            #         company_to.display_name,
            #     )
            #     continue
            #
            # existing = Move.search(
            #     [
            #         ("company_id", "=", company_to.id),
            #         ("journal_id", "=", dest_journal.id),
            #         ("ref", "=", payment.ref or payment.name or payment.communication),
            #         ("amount_total_signed", "=", abs(payment.amount)),
            #     ],
            #     limit=1,
            # )
            # if existing:
            #     continue
            #
            # amount = payment.amount
            #
            # move_vals = {
            #     "date": payment.date,
            #     "ref": payment.ref
            #     or payment.name
            #     or payment.communication
            #     or "Transferencia entre sucursales",
            #     "journal_id": dest_journal.id,
            #     "company_id": company_to.id,
            #     "line_ids": [
            #         (
            #             0,
            #             0,
            #             {
            #                 "name": "Transferencia entre sucursales",
            #                 "account_id": dest_journal.default_account_id.id,
            #                 "debit": amount,
            #                 "credit": 0.0,
            #                 "partner_id": payment.partner_id.id or False,
            #             },
            #         ),
            #         (
            #             0,
            #             0,
            #             {
            #                 "name": "Transferencia entre sucursales",
            #                 "account_id": bridge_account.id,
            #                 "debit": 0.0,
            #                 "credit": amount,
            #                 "partner_id": payment.partner_id.id or False,
            #             },
            #         ),
            #     ],
            # }
            #
            # move = (
            #     Move.with_context(no_interbranch_counterpart=True)
            #     .with_company(company_to.id)
            #     .create(move_vals)
            # )
            # move.action_post()
            #
            # _logger.info(
            #     "Creado asiento espejo %s en compañía %s para la "
            #     "transferencia de liquidez del pago %s.",
            #     move.name,
            #     company_to.display_name,
            #     payment.name or payment.id,
            # )
