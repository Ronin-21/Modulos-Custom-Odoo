# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from .prs_utils import prs_is_pos, prs_vals_look_like_pos, prs_journal_uses_receivable

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # Tipos de diarios donde aplica la lógica de extractos automáticos.
    _PRS_AUTO_EXTRACT_TYPES = ('cash', 'bank', 'credit_card')

    prs_expense_concept_id = fields.Many2one(
        'prs.expense.concept',
        string="Concepto de gasto",
        help="Clasificación de gastos (Concepto/Subconcepto).",
        index=True,
    )

    prs_statement_id = fields.Many2one(
        'account.bank.statement',
        string="Asignar en Estado de Cuenta",
        help="Permite asignar el extracto generado por este pago a un Estado de Cuenta específico (solo abiertos).",
    )

    # =========================================================================
    # Onchanges
    # =========================================================================

    @api.onchange('partner_id')
    def _onchange_partner_id_prs_expense_concept(self):
        for pay in self:
            if pay.partner_id and not pay.prs_expense_concept_id and getattr(
                pay.partner_id, 'prs_expense_concept_id', False
            ):
                pay.prs_expense_concept_id = pay.partner_id.prs_expense_concept_id

    @api.onchange('journal_id')
    def _onchange_journal_id_prs_statement(self):
        for pay in self:
            pay.prs_statement_id = False
            if not pay.journal_id:
                continue
            if pay.journal_id.type not in self._PRS_AUTO_EXTRACT_TYPES:
                continue
            if not getattr(pay.journal_id, 'auto_extract_enabled', False):
                continue
            if not pay.env.user.has_group(
                'payment_register_statement.group_prs_assign_payments_to_statements'
            ):
                continue
            Statement = pay.env['account.bank.statement']
            domain = [('journal_id', '=', pay.journal_id.id)]
            if 'prs_state' in Statement._fields:
                domain.append(('prs_state', '=', 'open'))
            stmt = Statement.search(domain, order='date desc, id desc', limit=1)
            pay.prs_statement_id = stmt

    # =========================================================================
    # create / write — solo validaciones
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        # Validación de permisos para prs_statement_id
        if any('prs_statement_id' in v for v in vals_list) and not self.env.user.has_group(
            'payment_register_statement.group_prs_assign_payments_to_statements'
        ):
            raise ValidationError("No tiene permisos para asignar pagos a Estados de Cuenta.")

        # POS: asignar partner de la compañía si el pago no trae contacto
        is_pos_ctx = prs_is_pos(self.env)
        for vals in vals_list:
            if vals.get('partner_id'):
                continue
            if is_pos_ctx or prs_vals_look_like_pos(vals):
                company = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id
                )
                if company and company.partner_id:
                    vals['partner_id'] = company.partner_id.id

        payments = super().create(vals_list)

        # Default concepto gasto desde el contacto
        for payment, vals in zip(payments, vals_list):
            if (
                not vals.get('prs_expense_concept_id')
                and payment.partner_id
                and getattr(payment.partner_id, 'prs_expense_concept_id', False)
            ):
                payment.prs_expense_concept_id = payment.partner_id.prs_expense_concept_id

        # Validación multiempresa: solo diarios de tipo EFECTIVO
        for payment in payments:
            payment._prs_check_multicompany_journal()

        return payments

    def write(self, vals):
        if 'prs_statement_id' in vals and not self.env.user.has_group(
            'payment_register_statement.group_prs_assign_payments_to_statements'
        ):
            raise ValidationError("No tiene permisos para asignar pagos a Estados de Cuenta.")

        res = super().write(vals)

        # Validación multiempresa: solo cuando cambia el diario
        if 'journal_id' in vals:
            for payment in self:
                payment._prs_check_multicompany_journal()

        return res

    # =========================================================================
    # action_post — orquestador liviano
    # =========================================================================

    def action_post(self):
        _logger.info("PRS: action_post para pagos %s", self.ids)

        # 1) Asegurar partner en pagos POS antes de postear
        self._prs_assign_pos_partner()

        # 2) Advertencia de memo faltante (no bloqueante)
        self._prs_warn_missing_memo()

        res = super().action_post()

        # 3) Si venimos desde conciliación, el extracto ya existe
        if self.env.context.get('from_statement_reconciliation'):
            return res

        # 4) Crear líneas de extracto para cada pago habilitado
        enabled = self.filtered(
            lambda p: p.journal_id.type in self._PRS_AUTO_EXTRACT_TYPES
            and p.journal_id.auto_extract_enabled
        )
        for payment in enabled:
            payment._prs_create_statement_lines()

        return res

    # =========================================================================
    # Helpers de action_post — ahora métodos del modelo, sobreescribibles
    # =========================================================================

    def _prs_assign_pos_partner(self):
        """Asigna el partner de la empresa a pagos POS que no traen contacto."""
        is_pos_ctx = prs_is_pos(self.env)
        for payment in self:
            if payment.partner_id:
                continue
            probe = {
                'memo': getattr(payment, 'memo', False),
                'ref': getattr(payment, 'ref', False),
                'payment_reference': getattr(payment, 'payment_reference', False),
                'communication': getattr(payment, 'communication', False),
                'name': payment.name,
            }
            if is_pos_ctx or prs_vals_look_like_pos(probe):
                company = payment.company_id or self.env.company
                if company and company.partner_id:
                    payment.partner_id = company.partner_id

    def _prs_warn_missing_memo(self):
        """Envía notificación de bus si falta el Memo (configurable por diario)."""
        for payment in self:
            # Respetar el flag prs_warn_missing_memo del diario (default True)
            if not getattr(payment.journal_id, 'prs_warn_missing_memo', True):
                continue
            if not payment.memo:
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id,
                    'simple_notification',
                    {
                        'title': "Campo requerido",
                        'message': "⚠️ El pago %s no tiene 'Memo' definido. Se recomienda completarlo." % payment.name,
                        'sticky': False,
                        'type': 'warning',
                    }
                )

    def _prs_get_payment_label(self):
        """Retorna la etiqueta canónica del pago para usar en el extracto.

        Centraliza la lógica del prefijo [GV] para que todos los lugares
        (crear extracto, buscar extracto, limpiar extracto) usen exactamente
        la misma cadena.
        """
        self.ensure_one()
        label = (
            self.memo
            or getattr(self, 'communication', False)
            or self.name
            or 'Sin referencia'
        )
        if getattr(self, 'prs_is_misc_expense', False) and label and not str(label).startswith('[GV]'):
            label = f"[GV] {label}"
        return label

    def _prs_should_skip_pos_receivable(self, journal):
        """Determina si se debe omitir el extracto por ser POS con cuenta Por Cobrar.

        Flujo tarjetas: el POS registra el cargo en una cuenta receivable
        (ej. Tarjetas a cobrar). El banco no se toca hasta que el proveedor
        de tarjetas acredita. Por eso no creamos extracto bancario aquí.
        """
        self.ensure_one()
        probe = {
            'memo': getattr(self, 'memo', False),
            'name': self.name,
            'ref': getattr(self, 'ref', False),
            'payment_reference': getattr(self, 'payment_reference', False),
        }
        is_pos = prs_is_pos(self.env) or prs_vals_look_like_pos(probe)
        return is_pos and prs_journal_uses_receivable(journal)

    def _prs_get_statement_for_payment(self, journal):
        """Retorna el Estado de Cuenta a usar para este pago en el diario dado.

        Prioridad:
        1. Estado de Cuenta elegido manualmente por el usuario (prs_statement_id).
        2. Último Estado de Cuenta ABIERTO del diario.
        3. False si no hay ninguno usable.
        """
        self.ensure_one()

        if getattr(self, 'prs_statement_id', False):
            st = self.prs_statement_id
            if st.journal_id.id != journal.id:
                raise ValidationError(
                    "El Estado de Cuenta seleccionado no pertenece al diario del pago."
                )
            if 'prs_state' in st._fields and st.prs_state == 'closed':
                raise ValidationError(
                    "No se puede asignar un pago a un Estado de Cuenta CERRADO."
                )
            return st

        return self._prs_get_last_statement_for_journal(journal)

    def _prs_get_last_statement_for_journal(self, journal):
        """Busca el último Estado de Cuenta usable del diario (sin crear uno nuevo)."""
        Statement = self.env['account.bank.statement'].with_company(journal.company_id)

        for field, domain_extra in [
            ('prs_state',  [('prs_state', '=', 'open')]),
            ('state',      [('state', 'not in', ('close', 'closed'))]),
            ('status',     [('status', 'in', ('draft', 'open'))]),
            ('move_state', [('move_state', 'in', ('draft', 'open'))]),
        ]:
            if field in Statement._fields:
                stmt = Statement.search(
                    [('journal_id', '=', journal.id)] + domain_extra,
                    order='date desc, id desc', limit=1,
                )
                return stmt or False

        # Último recurso: sin filtro de estado
        return Statement.search(
            [('journal_id', '=', journal.id)], order='date desc, id desc', limit=1
        ) or False

    def _prs_existing_statement_line(self, LineModel, journal, label, amount_signed):
        """Idempotencia: detecta si ya existe una línea de extracto para este pago."""
        self.ensure_one()

        # La forma más confiable: buscar por payment_id si el campo existe
        if 'payment_id' in LineModel._fields:
            existing = LineModel.search([
                ('payment_id', '=', self.id),
                ('journal_id', '=', journal.id),
            ], limit=1)
            if existing:
                return existing

        # Fallback: match por fecha, importe, label y partner
        dom = [
            ('journal_id', '=', journal.id),
            ('date', '=', self.date),
            ('amount', '=', amount_signed),
        ]
        if self.partner_id:
            dom.append(('partner_id', '=', self.partner_id.id))
        if 'name' in LineModel._fields:
            dom += ['|', ('payment_ref', '=', label), ('name', '=', label)]
        else:
            dom.append(('payment_ref', '=', label))

        return LineModel.search(dom, limit=1)

    def _prs_get_check_lines(self, sign):
        """Retorna una línea por cheque si el pago tiene múltiples cheques l10n_latam.

        Solo actúa cuando el diario tiene activado prs_split_checks_per_statement.
        Si el flag está desactivado o hay un solo cheque, retorna lista vacía
        y el flujo normal crea un único extracto por el total del pago.

        Soporta:
        - l10n_latam_new_check_ids: cheques propios / nuevos de terceros
        - l10n_latam_move_check_ids: cheques existentes de terceros en cartera
        """
        self.ensure_one()

        # Flag configurable por diario — si no está activo, flujo normal
        if not getattr(self.journal_id, 'prs_split_checks_per_statement', False):
            return []

        new_checks  = getattr(self, 'l10n_latam_new_check_ids',  False)
        move_checks = getattr(self, 'l10n_latam_move_check_ids', False)

        source = None
        if new_checks and len(new_checks) > 1:
            source = new_checks
        elif move_checks and len(move_checks) > 1:
            source = move_checks

        if not source:
            return []

        return [
            {
                'amount': sign * check.amount,
                'label': getattr(check, 'name', False) or self.name or 'Cheque',
            }
            for check in source
        ]

    def _prs_build_base_statement_vals(self, journal, statement, label, amount_signed):
        """Construye el dict base de valores para una línea de extracto."""
        self.ensure_one()
        LineModel = self.env['account.bank.statement.line']

        vals = {
            'date': self.date,
            'payment_ref': label,
            'partner_id': self.partner_id.id or False,
            'amount': amount_signed,
            'foreign_currency_id': self.currency_id.id or False,
            'amount_currency': amount_signed if self.currency_id else 0.0,
            'company_id': journal.company_id.id,
            'journal_id': journal.id,
        }

        if 'name' in LineModel._fields:
            vals['name'] = label
        if statement:
            vals['statement_id'] = statement.id

        # Propagar concepto de gasto si existe el campo en la línea
        if 'prs_expense_concept_id' in LineModel._fields:
            try:
                if getattr(self, 'prs_expense_concept_id', False):
                    vals['prs_expense_concept_id'] = self.prs_expense_concept_id.id
            except Exception:
                pass

        return vals

    def _prs_recompute_statement(self, statement):
        """Recalcula saldos del Estado de Cuenta tras crear una línea."""
        if not statement:
            return
        try:
            if (
                getattr(statement.journal_id, 'prs_auto_statement_balance', False)
                and getattr(statement, 'prs_state', 'open') == 'open'
            ):
                statement._prs_recompute_balances(start_from=statement)
            else:
                if hasattr(statement, '_compute_balance_end_real'):
                    statement._compute_balance_end_real()
                if hasattr(statement, '_compute_difference'):
                    statement._compute_difference()
        except Exception as e:
            _logger.warning(
                "PRS: no se pudo recalcular saldo del estado de cuenta %s: %s",
                getattr(statement, 'name', statement.id), e,
            )

    def _prs_create_statement_lines(self):
        """Punto de entrada principal para crear las líneas de extracto de este pago.

        Lógica:
        1. Verificar que el diario aplica (tipo + auto_extract_enabled).
        2. Skip si es POS con cuenta Por Cobrar.
        3. Idempotencia: skip si ya existe una línea para este pago.
        4. Si el diario tiene prs_split_checks_per_statement y hay múltiples cheques
           → crear una línea por cheque.
        5. Caso general → crear una línea por el total del pago.
        """
        self.ensure_one()

        journal = self.journal_id
        if journal.type not in self._PRS_AUTO_EXTRACT_TYPES or not journal.auto_extract_enabled:
            return

        sign = 1 if self.payment_type == 'inbound' else -1
        amount_signed = sign * self.amount
        label = self._prs_get_payment_label()

        LineModel = self.env['account.bank.statement.line'].with_company(journal.company_id)

        # ── Skip: POS con cuenta Por Cobrar ─────────────────────────────────
        if self._prs_should_skip_pos_receivable(journal):
            _logger.info(
                "PRS: pago POS %s en diario con cuenta Por Cobrar '%s' → "
                "se omite creacion de extracto bancario.",
                self.name, journal.name,
            )
            return

        # ── Idempotencia ─────────────────────────────────────────────────────
        existing = self._prs_existing_statement_line(LineModel, journal, label, amount_signed)
        if existing:
            _logger.info(
                "PRS: extracto duplicado omitido para pago %s en diario %s (línea %s ya existe)",
                self.name, journal.name, existing.id,
            )
            return

        # ── Estado de Cuenta a usar ──────────────────────────────────────────
        statement = self._prs_get_statement_for_payment(journal)
        base_vals = self._prs_build_base_statement_vals(journal, statement, label, amount_signed)

        # ── Múltiples cheques: un extracto por cheque ────────────────────────
        check_lines = self._prs_get_check_lines(sign)
        if check_lines:
            for check_data in check_lines:
                check_vals = dict(base_vals)
                check_vals['amount'] = check_data['amount']
                check_vals['payment_ref'] = check_data['label']
                check_vals['amount_currency'] = check_data['amount'] if self.currency_id else 0.0
                if 'name' in LineModel._fields:
                    check_vals['name'] = check_data['label']
                # No seteamos payment_id en extractos por cheque individual para
                # evitar que el check de idempotencia los bloquee en pagos futuros
                LineModel.create(check_vals)
                _logger.info(
                    "PRS: extracto por cheque '%s' ($%s) en diario %s",
                    check_data['label'], check_data['amount'], journal.name,
                )
            self._prs_recompute_statement(statement)
            return

        # ── Flujo normal: un extracto por pago ──────────────────────────────
        vals = dict(base_vals)
        if 'payment_id' in LineModel._fields:
            vals['payment_id'] = self.id

        LineModel.create(vals)
        self._prs_recompute_statement(statement)
        _logger.info(
            "PRS: extracto creado en diario %s ($%s) [%s]",
            journal.name, amount_signed, 'adjunto a estado' if statement else 'independiente',
        )

    # =========================================================================
    # Validación multiempresa
    # =========================================================================

    def _prs_check_multicompany_journal(self):
        """Valida que el diario de EFECTIVO esté permitido para la empresa del pago."""
        self.ensure_one()
        journal = self.journal_id
        if (
            journal and journal.type == 'cash'
            and self.company_id != journal.company_id
            and self.company_id not in getattr(journal, 'allowed_company_ids', self.env['res.company'])
        ):
            raise ValidationError(
                "El diario %s no está permitido para la empresa %s."
                % (journal.name, self.company_id.display_name)
            )

    # =========================================================================
    # Protección y limpieza de extractos vinculados
    # =========================================================================

    def _get_statement_lines_for_payment(self):
        """Obtiene las líneas de extracto creadas por este pago."""
        Line = self.env['account.bank.statement.line']
        result = self.env['account.bank.statement.line']
        has_payment_id = 'payment_id' in Line._fields
        for payment in self:
            # Enlace directo y fiable: SOLO las líneas creadas por ESTE pago.
            # Se elimina el match por payment_ref/name: dos pagos de la misma
            # factura comparten memo (= nº de factura) y la búsqueda por etiqueta
            # arrastra la línea de OTRO pago (falso positivo en el bloqueo).
            if has_payment_id:
                result |= Line.search([('payment_id', '=', payment.id)])
                continue
            # Fallback legacy SOLO para instalaciones sin el campo payment_id.
            label = payment._prs_get_payment_label()
            result |= Line.search(['|', ('payment_ref', '=', label), ('name', '=', label)])
        return result

    def _block_if_reconciled_statement(self):
        """Evita borrar/restablecer un pago si sus extractos ya están conciliados."""
        lines = self._get_statement_lines_for_payment()
        if not lines:
            return
        reconciled = lines.filtered(lambda l: getattr(l, 'is_reconciled', False))
        if reconciled:
            raise ValidationError(
                "No se puede borrar / restablecer este pago porque el extracto asociado ya está conciliado.\n"
                "Primero deshaga la conciliación del estado de cuenta."
            )

    def _cleanup_related_statements(self):
        """Borra las líneas de extracto creadas por este pago."""
        for payment in self:
            # Mismo criterio seguro que el bloqueo: solo líneas de ESTE pago.
            lines = payment._get_statement_lines_for_payment()
            for line in lines:
                statement = line.statement_id
                line.with_context(allow_delete_from_payment=True).unlink()
                if statement and statement.exists():
                    if statement.line_ids:
                        try:
                            statement._compute_balance_end_real()
                            statement._compute_difference()
                        except Exception:
                            pass
                    else:
                        statement.with_context(allow_delete_from_payment=True).unlink()

    def action_draft(self):
        if not self.env.context.get('skip_statement_cleanup'):
            enabled = self.filtered(
                lambda p: p.journal_id
                and p.journal_id.type in self._PRS_AUTO_EXTRACT_TYPES
                and p.journal_id.auto_extract_enabled
            )
            if enabled:
                enabled._block_if_reconciled_statement()
                enabled._cleanup_related_statements()
        return super().action_draft()

    def unlink(self):
        if not self.env.context.get('skip_statement_cleanup'):
            enabled = self.filtered(
                lambda p: p.journal_id
                and p.journal_id.type in self._PRS_AUTO_EXTRACT_TYPES
                and p.journal_id.auto_extract_enabled
            )
            if enabled:
                enabled._block_if_reconciled_statement()
                enabled._cleanup_related_statements()
        return super().unlink()
