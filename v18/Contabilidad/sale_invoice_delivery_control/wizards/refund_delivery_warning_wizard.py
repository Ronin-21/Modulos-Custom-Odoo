from odoo import _, fields, models


class RefundDeliveryWarningWizard(models.TransientModel):
    """
    Wizard de bloqueo informativo: se muestra cuando el usuario intenta
    crear una NC pero no hay mercadería devuelta que acreditar.

    Es solo informativo: el usuario solo puede cerrar el wizard.
    La NC no se crea.
    """
    _name = 'refund.delivery.warning.wizard'
    _description = 'No se puede crear la Nota de Crédito'

    message = fields.Text(string='Motivo', readonly=True)
    delivery_summary = fields.Text(string='Entregas relacionadas', readonly=True)

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}
