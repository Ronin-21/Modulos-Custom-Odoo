from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    invoice_number_display = fields.Char(
        string='Facturación',
        compute='_compute_invoice_number_display',
        store=True,
        readonly=True,
        help='Muestra la numeración de las facturas publicadas vinculadas a esta orden de venta.',
    )

    invoice_afip_auth_display = fields.Char(
        string='CAE / ARCA',
        compute='_compute_invoice_afip_auth_display',
        store=True,
        readonly=True,
        help='Muestra el código de autorización fiscal (CAE/ARCA) de las facturas vinculadas. '
             'Solo disponible con localización argentina (l10n_ar).',
    )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_posted_customer_invoices(self):
        """Retorna las facturas de cliente publicadas vinculadas a la orden,
        ordenadas por fecha de factura (ascendente) y luego por ID."""
        self.ensure_one()
        return self.invoice_ids.filtered(
            lambda move: move.move_type == 'out_invoice'
            and move.state == 'posted'
        ).sorted(
            key=lambda m: (
                m.invoice_date or m.date or m.create_date,
                m.id,
            )
        )

    @staticmethod
    def _get_invoice_display_number(move):
        """Devuelve el mejor número de factura disponible para un asiento.

        Orden de prioridad:
        1. move.name  (nombre contable confirmado, ej. "FAC A 0001-00000543")
        2. l10n_latam_document_number  (fallback para localización latam)

        Retorna False si no hay número válido.
        """
        # 1) Nombre contable estándar
        if move.name and move.name != '/':
            return move.name

        # 2) Número de documento latinoamericano (fallback seguro)
        if 'l10n_latam_document_number' in move._fields:
            latam_number = move.l10n_latam_document_number
            if latam_number and latam_number != '/':
                return latam_number

        return False

    # -------------------------------------------------------------------------
    # Campos computados
    # -------------------------------------------------------------------------

    @api.depends(
        'invoice_ids',
        'invoice_ids.name',
        'invoice_ids.state',
        'invoice_ids.move_type',
        'invoice_ids.invoice_date',
    )
    def _compute_invoice_number_display(self):
        for order in self:
            numbers = []
            for move in order._get_posted_customer_invoices():
                number = self._get_invoice_display_number(move)
                if number:
                    numbers.append(number)
            order.invoice_number_display = ' / '.join(numbers) if numbers else False

    @api.depends(
        'invoice_ids',
        'invoice_ids.state',
        'invoice_ids.move_type',
    )
    def _compute_invoice_afip_auth_display(self):
        """Muestra el código CAE/ARCA de autorización fiscal.

        Este campo depende de campos de localización argentina (l10n_ar).
        Si esos campos no existen en la base de datos, el campo queda vacío
        sin lanzar ningún error.
        """
        # Detectar de antemano si los campos existen para no iterar
        # campo a campo en el bucle interno (optimización).
        invoice_model = self.env['account.move']
        has_auth_code = 'l10n_ar_afip_auth_code' in invoice_model._fields
        has_auth_mode = 'l10n_ar_afip_auth_mode' in invoice_model._fields

        for order in self:
            if not has_auth_code:
                order.invoice_afip_auth_display = False
                continue

            codes = []
            for move in order._get_posted_customer_invoices():
                auth_code = move.l10n_ar_afip_auth_code
                if not auth_code:
                    continue

                if has_auth_mode and move.l10n_ar_afip_auth_mode:
                    # Ej: "CAE: 12345678901234"
                    label = move.l10n_ar_afip_auth_mode.upper()
                    codes.append('{}: {}'.format(label, auth_code))
                else:
                    codes.append(auth_code)

            order.invoice_afip_auth_display = ' / '.join(codes) if codes else False
