# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


from .prs_utils import prs_is_pos


# =====================================================================
# LÍNEAS DE EXTRACTO
# =====================================================================
class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    payment_id = fields.Many2one("account.payment", string="Pago origen", readonly=True)

    def _prs_is_statement_closed(self, statement):
        # Si el modelo de estado de cuenta tiene el campo prs_state, lo usamos.
        if statement and 'prs_state' in statement._fields:
            return statement.prs_state == 'closed'
        # Fallback: estados estándar si existieran
        if statement and 'state' in statement._fields:
            return statement.state in ('close', 'closed')
        return False

    @api.model_create_multi
    def create(self, vals_list):
        Statement = self.env['account.bank.statement']

        for vals in vals_list:
            st_id = vals.get('statement_id')

            # ── Validación: no crear dentro de un estado CERRADO ──────────────
            if st_id:
                st = Statement.browse(st_id)
                if self._prs_is_statement_closed(st):
                    raise ValidationError("No se pueden agregar extractos a un Estado de Cuenta CERRADO.")
                continue  # ya tiene estado asignado, nada más que hacer

            # ── Auto-asignación para diarios con auto_extract_enabled ─────────
            # Solo aplica cuando:
            #   · La línea NO viene con statement_id (creación manual / wizard externo)
            #   · El diario tiene auto_extract_enabled activo
            # Objetivo: evitar líneas huérfanas que queden fuera del cálculo de
            # saldos (_prs_recompute_balances solo procesa line_ids de un estado).\n
            journal_id = vals.get('journal_id')
            if not journal_id:
                continue

            journal = self.env['account.journal'].browse(journal_id)
            if not getattr(journal, 'auto_extract_enabled', False):
                continue

            line_date = vals.get('date') or fields.Date.today()

            # Candidato principal: estado ABIERTO del mismo diario cuya fecha
            # sea <= a la línea (el más reciente que "cubre" esa fecha).
            best = Statement.search([
                ('journal_id', '=', journal_id),
                ('prs_state', '=', 'open'),
                ('date', '<=', line_date),
            ], order='date desc, id desc', limit=1)

            if best:
                vals['statement_id'] = best.id
                _logger.info(
                    "PRS: línea manual en diario '%s' (fecha %s) auto-asignada al "
                    "estado '%s' (id=%s).",
                    journal.name, line_date, best.name or best.id, best.id,
                )
                continue

            # Fallback: si la línea es anterior al primer estado abierto
            # (p.ej. alguien carga un movimiento con fecha vieja), la asignamos
            # al estado abierto más antiguo del diario para no dejarla huérfana.
            fallback = Statement.search([
                ('journal_id', '=', journal_id),
                ('prs_state', '=', 'open'),
            ], order='date asc, id asc', limit=1)

            if fallback:
                vals['statement_id'] = fallback.id
                _logger.warning(
                    "PRS: línea manual en diario '%s' (fecha %s) no coincide con "
                    "ningún estado abierto por fecha. Asignada al estado más antiguo "
                    "abierto '%s' (id=%s) como fallback.",
                    journal.name, line_date, fallback.name or fallback.id, fallback.id,
                )
            else:
                # Sin estados abiertos: la línea queda huérfana.
                # No bloqueamos — el usuario deberá crear un estado de cuenta primero.
                _logger.warning(
                    "PRS: línea manual en diario '%s' (fecha %s) quedó huérfana: "
                    "no existe ningún Estado de Cuenta ABIERTO para ese diario. "
                    "Creá un estado de cuenta y reasignála.",
                    journal.name, line_date,
                )

        lines = super().create(vals_list)

        # Recalcular saldos automáticos si aplica
        statements = lines.mapped('statement_id')
        if statements:
            try:
                statements._prs_recompute_balances()
            except Exception:
                _logger.warning("PRS: error al recalcular saldos tras crear líneas de extracto", exc_info=True)

        return lines


    def write(self, vals):
        # Bloqueo: no permitir modificar líneas de un Estado de Cuenta CERRADO.
        if any(self._prs_is_statement_closed(l.statement_id) for l in self.filtered(lambda x: x.statement_id)):
            raise ValidationError("No se pueden modificar extractos de un Estado de Cuenta CERRADO.")

        # Si se intenta mover la línea a otro Estado de Cuenta, validar que esté ABIERTO.
        if vals.get('statement_id'):
            st = self.env['account.bank.statement'].browse(vals['statement_id'])
            if self._prs_is_statement_closed(st):
                raise ValidationError("No se pueden agregar extractos a un Estado de Cuenta CERRADO.")

        res = super().write(vals)
        # Recalcular saldos automáticos si aplica
        try:
            self.mapped('statement_id')._prs_recompute_balances()
        except Exception:
            _logger.warning("PRS: error al recalcular saldos tras modificar línea de extracto", exc_info=True)

        return res

    def _validate_related_payments_after_reconcile(self):
        Payment = self.env["account.payment"]
        for line in self:
            # Solo aplica cuando el diario del extracto tiene activada la opción
            # "Crear extractos automáticos". Si está apagada, no validamos pagos
            # automáticamente al conciliar.
            journal = (line.statement_id.journal_id if line.statement_id else line.journal_id)
            auto_types = getattr(Payment, '_PRS_AUTO_EXTRACT_TYPES', ('cash', 'bank', 'credit_card'))
            if not (journal and journal.type in auto_types and getattr(journal, 'auto_extract_enabled', False)):
                continue
            if not getattr(line, "is_reconciled", False):
                continue

            payments = Payment.browse()
            # 1) Enlace directo
            if "payment_id" in line._fields and line.payment_id:
                payments = line.payment_id
            else:
                refs = []
                if line.payment_ref:
                    refs.append(line.payment_ref)
                if getattr(line, "name", False):
                    refs.append(line.name)

                if refs:
                    conds = []
                    if "memo" in Payment._fields:
                        conds.append(("memo", "in", refs))
                    if "name" in Payment._fields:
                        conds.append(("name", "in", refs))
                    if "communication" in Payment._fields:
                        conds.append(("communication", "in", refs))

                    if conds:
                        domain = conds[0]
                        for c in conds[1:]:
                            domain = ["|", domain, c]
                        payments = Payment.search(domain)

                if not payments:
                    amount = abs(line.amount)
                    journal = line.statement_id.journal_id or line.journal_id
                    domain = [
                        ("state", "in", ["draft", "in_process", "en_proceso"]),
                        ("amount", "=", amount),
                    ]
                    if journal:
                        domain.append(("journal_id", "=", journal.id))
                    if line.partner_id:
                        domain.append(("partner_id", "=", line.partner_id.id))
                    payments = Payment.search(domain)

            for pay in payments:
                if pay.state in ("paid", "pagado", "reconciled", "posted"):
                    continue
                ctx = {
                    "from_statement_reconciliation": True,
                    "skip_statement_cleanup": True,
                }
                try:
                    if hasattr(pay, "action_validate"):
                        pay.with_context(**ctx).action_validate()
                    else:
                        pay.with_context(**ctx).action_post()
                    _logger.info(
                        "Pago %s validado automáticamente al conciliar la línea de extracto %s.",
                        pay.name, line.id
                    )
                except Exception as e:
                    _logger.warning(
                        "No se pudo validar el pago %s desde la línea de extracto %s: %s",
                        pay.name, line.id, e
                    )

    def unlink(self):
        # Bloqueo: no permitir borrar extractos de un Estado de Cuenta CERRADO.
        if any(self._prs_is_statement_closed(l.statement_id) for l in self.filtered(lambda x: x.statement_id)):
            raise ValidationError("No se pueden eliminar extractos de un Estado de Cuenta CERRADO.")

        statements = self.mapped('statement_id')
        if prs_is_pos(self.env):
            res = super().unlink()
            # Recalcular saldos automáticos si aplica
            try:
                statements._prs_recompute_balances()
            except Exception:
                pass
            return res
        if self.env.context.get("allow_delete_from_payment"):
            return super().unlink()

        Payment = self.env["account.payment"]
        for line in self:
            linked_payment = False
            if "payment_id" in line._fields and line.payment_id:
                linked_payment = True
            else:
                refs = []
                if line.payment_ref:
                    refs.append(line.payment_ref)
                if getattr(line, "name", False):
                    refs.append(line.name)
                if refs:
                    conds = []
                    if "memo" in Payment._fields:
                        conds.append(("memo", "in", refs))
                    if "name" in Payment._fields:
                        conds.append(("name", "in", refs))
                    if "communication" in Payment._fields:
                        conds.append(("communication", "in", refs))
                    if conds:
                        domain = conds[0]
                        for c in conds[1:]:
                            domain = ["|", domain, c]
                        if Payment.search(domain, limit=1):
                            linked_payment = True

            journal = (line.statement_id.journal_id if line.statement_id else line.journal_id)
            auto_types = getattr(Payment, '_PRS_AUTO_EXTRACT_TYPES', ('cash', 'bank', 'credit_card'))
            if linked_payment and (journal and journal.type in auto_types and getattr(journal, 'auto_extract_enabled', False)):
                raise ValidationError(
                    "Esta línea de estado de cuenta se creó desde un pago.\n"
                    "Bórrala desde el pago (restablecer/borrar) para mantener la coherencia."
                )
        return super().unlink()


# =====================================================================
# CABECERA DE EXTRACTO
# =====================================================================
class AccountBankStatement(models.Model):
    _inherit = "account.bank.statement"


    prs_state = fields.Selection(
        selection=[('open', 'Abierto'), ('closed', 'Cerrado')],
        string="Estado",
        default='open',
        copy=False,
    )

    # Campo relacionado simple (sin notación con puntos) para usar en vistas
    # (en varias bases, `journal_id.prs_auto_statement_balance` en expresiones
    # de vista puede no evaluarse bien y deja los campos siempre en readonly).
    prs_auto_statement_balance_active = fields.Boolean(
        string="Cálculo automático activo",
        related="journal_id.prs_auto_statement_balance",
        readonly=True,
    )

    # Marca cuando el usuario define manualmente el saldo inicial del PRIMER
    # estado de cuenta ABIERTO del diario (con cálculo automático activo).
    # Para los demás estados, el saldo inicial siempre se encadena desde el
    # saldo final del estado anterior.
    prs_balance_start_manual = fields.Boolean(
        string="Saldo inicial manual",
        default=False,
        copy=False,
    )

    # True solo para el primer estado de cuenta ABIERTO del diario cuando el
    # cálculo automático está activo en el diario.
    prs_is_first_open_auto = fields.Boolean(
        string="Es primer estado abierto",
        compute="_compute_prs_is_first_open_auto",
        store=False,
    )

    def _compute_prs_is_first_open_auto(self):
        """Determina el primer estado ABIERTO del diario.

        Regla: solo aplica cuando el diario tiene `prs_auto_statement_balance` activo.
        """
        Statement = self.env['account.bank.statement']
        # Agrupar por diario para reducir búsquedas
        by_journal = {}
        for st in self:
            by_journal.setdefault(st.journal_id.id if st.journal_id else False, []).append(st)

        for journal_id, records in by_journal.items():
            # Si no hay diario, todos False
            if not journal_id:
                for st in records:
                    st.prs_is_first_open_auto = False
                continue

            journal = records[0].journal_id
            if not getattr(journal, 'prs_auto_statement_balance', False):
                for st in records:
                    st.prs_is_first_open_auto = False
                continue

            first = Statement.search([
                ('journal_id', '=', journal_id),
                ('prs_state', '=', 'open'),
            ], order='date asc, id asc', limit=1)

            for st in records:
                st.prs_is_first_open_auto = bool(first and first.id == st.id and st.prs_state == 'open')

    def _prs_is_first_open_auto_runtime(self):
        """Helper runtime (incluye casos sin ID aún)."""
        self.ensure_one()
        if not self.journal_id or not getattr(self.journal_id, 'prs_auto_statement_balance', False):
            return False
        if getattr(self, 'prs_state', 'open') != 'open':
            return False

        Statement = self.env['account.bank.statement']
        # Si es nuevo (sin id), será "primero" solo si no hay otros abiertos.
        if not self.id:
            first = Statement.search([
                ('journal_id', '=', self.journal_id.id),
                ('prs_state', '=', 'open'),
            ], order='date asc, id asc', limit=1)
            return not bool(first)

        first = Statement.search([
            ('journal_id', '=', self.journal_id.id),
            ('prs_state', '=', 'open'),
        ], order='date asc, id asc', limit=1)
        return bool(first and first.id == self.id)


    # ------------------------------
    # UI dinámico (sin recargar)
    # ------------------------------
    @api.onchange('journal_id', 'date')
    def _onchange_prs_auto_balance_header(self):
        """Actualiza saldo inicial/final en el formulario cuando cambia el diario o la fecha."""
        for st in self:
            st._prs_onchange_recompute_balances()

    @api.onchange('line_ids', 'line_ids.amount', 'line_ids.is_reconciled', 'line_ids.move_id')
    def _onchange_prs_auto_balance_lines(self):
        """Actualiza saldo inicial/final en el formulario al agregar/quitar/modificar extractos.

        Incluye cambios en subcampos relevantes porque, al conciliar una línea desde la
        propia vista del estado de cuenta, Odoo suele actualizar `is_reconciled` / `move_id`
        sin disparar siempre un onchange puro sobre `line_ids`.
        """
        for st in self:
            st._prs_onchange_recompute_balances()

    @api.onchange('balance_start')
    def _onchange_prs_balance_start_manual(self):
        """Si el usuario modifica el saldo inicial, lo marcamos como manual.

        Aplica únicamente al PRIMER estado de cuenta ABIERTO del diario cuando
        el diario tiene cálculo automático activo.
        """
        for st in self:
            if st.journal_id and getattr(st.journal_id, 'prs_auto_statement_balance', False) and st._prs_is_first_open_auto_runtime():
                st.prs_balance_start_manual = True

    def _prs_should_count_line_in_balance(self, line):
        """Define si una línea es reconciliada (para balance_end_real)."""
        self.ensure_one()
        if not line:
            return False
        if 'is_reconciled' in line._fields:
            return bool(getattr(line, 'is_reconciled', False))
        if 'move_id' in line._fields:
            return bool(getattr(line, 'move_id', False))
        return True

    def _compute_balance_end(self):
        # Invalidar el caché ORM de balance_start antes del compute nativo.
        # PRS escribe balance_start con check_move_validity=False, lo que puede
        # dejar un valor cacheado desactualizado. La invalidación fuerza la
        # re-lectura desde DB, evitando el aviso naranja en Cajas Registradoras.
        if self:
            self.invalidate_recordset(['balance_start'])
        super()._compute_balance_end()

    def _prs_get_lines_total(self, only_reconciled=None):
        """Suma los importes de las líneas del estado.

        Si only_reconciled=True (o el diario tiene prs_only_reconciled_statements),
        solo suma las líneas ya conciliadas — usado para balance_end_real.

        Si only_reconciled=False, suma todas las líneas — usado para balance_start
        del siguiente estado (para que el running_balance de Odoo sea correcto).
        """
        self.ensure_one()
        if only_reconciled is None:
            only_reconciled = bool(
                getattr(self.journal_id, 'prs_only_reconciled_statements', False)
            )
        if only_reconciled:
            lines = self.line_ids.filtered(self._prs_should_count_line_in_balance)
        else:
            lines = self.line_ids
        return sum(lines.mapped('amount'))

    def _prs_onchange_recompute_balances(self):
        """Recalcula en memoria (onchange) para que el usuario vea el saldo al instante.

        Nota: esto NO reemplaza el recálculo persistente; solo evita que el usuario tenga
        que recargar la vista para ver el saldo.
        """
        self.ensure_one()
        # Solo cuando el diario tiene saldo automático activo y el estado está abierto
        if not self.journal_id or not getattr(self.journal_id, 'prs_auto_statement_balance', False):
            return
        if getattr(self, 'prs_state', 'open') != 'open':
            return

        Statement = self.env['account.bank.statement']
        is_first_open = self._prs_is_first_open_auto_runtime()

        # Buscar el estado anterior del mismo diario
        if self.id:
            prev_domain = [
                ('journal_id', '=', self.journal_id.id),
                ('id', '!=', self.id),
                '|',
                ('date', '<', self.date),
                '&', ('date', '=', self.date), ('id', '<', self.id),
            ]
        else:
            prev_domain = [
                ('journal_id', '=', self.journal_id.id),
                ('date', '<', self.date),
            ]
        prev = Statement.search(prev_domain, order='date desc, id desc', limit=1)

        computed_start = 0.0
        if prev:
            if 'balance_end_real' in prev._fields and prev.balance_end_real is not False:
                computed_start = prev.balance_end_real
            elif 'balance_end' in prev._fields and prev.balance_end is not False:
                computed_start = prev.balance_end

        # Si es el primer estado abierto y el usuario definió manualmente el saldo inicial,
        # respetamos ese valor. Caso contrario, encadenamos desde el estado anterior.
        if is_first_open and self.prs_balance_start_manual:
            start = float(self.balance_start or 0.0)
        else:
            start = computed_start
            self.balance_start = start

        # balance_end_real: solo reconciliados si el flag está activo
        only_reconciled = bool(getattr(self.journal_id, 'prs_only_reconciled_statements', False))
        total_for_end = self._prs_get_lines_total(only_reconciled=only_reconciled)

        self.balance_start = start
        if 'balance_end_real' in self._fields:
            self.balance_end_real = start + total_for_end


    def action_prs_close_statement(self):
        # Antes de cerrar, si el diario tiene saldo automático, dejamos los saldos al día.
        try:
            self._prs_recompute_balances()
        except Exception:
            _logger.warning("PRS: error al recalcular saldos antes de cerrar estado de cuenta %s", self.ids, exc_info=True)
        self.write({'prs_state': 'closed'})
        return True

    def action_prs_reopen_statement(self):
        # Reabrir solo por Administrador de Contabilidad.
        if not self.env.user.has_group('account.group_account_manager'):
            raise ValidationError("No tiene permisos para reabrir un Estado de Cuenta.")
        self.write({'prs_state': 'open'})
        return True

    def action_prs_recompute_balances(self):
        """Botón manual: recalcula balance_end_real y balance_end en cadena.

        Opera directamente sin depender del flag prs_auto_statement_balance,
        por lo que funciona en cualquier diario. Corrige el aviso naranja de
        Odoo "balance en ejecución no coincide" incluso cuando el flag automático
        no está activo o cuando los saldos quedaron desactualizados.

        Algoritmo:
        1. Determina el saldo base (último estado CERRADO anterior, o balance_start actual).
        2. Recorre en orden todos los estados ABIERTOS desde este en adelante.
        3. Para cada uno: balance_end_real = balance_start + suma(todas las líneas).
        4. Actualiza balance_end en SQL para que Odoo no muestre el aviso naranja.
        5. Encadena balance_start del siguiente estado con el balance_end de este.
        """
        Statement = self.env['account.bank.statement']

        for st in self:
            if getattr(st, 'prs_state', 'open') == 'closed':
                continue
            if not st.journal_id:
                continue

            # Saldo base: balance_end_real del último cerrado anterior, o balance_start actual
            prev_closed = Statement.search([
                ('journal_id', '=', st.journal_id.id),
                ('prs_state', '=', 'closed'),
                '|',
                ('date', '<', st.date),
                '&', ('date', '=', st.date), ('id', '<', st.id),
            ], order='date desc, id desc', limit=1)

            if prev_closed:
                chain_start = float(prev_closed.balance_end_real or prev_closed.balance_start or 0.0)
            else:
                chain_start = float(st.balance_start or 0.0)

            # Estados abiertos desde este en adelante (incluye el actual)
            open_from_here = Statement.search([
                ('journal_id', '=', st.journal_id.id),
                ('prs_state', '=', 'open'),
                '|',
                ('date', '>', st.date),
                '&', ('date', '=', st.date), ('id', '>', st.id),
            ], order='date asc, id asc')
            open_chain = st | open_from_here

            last_end = chain_start
            for open_st in open_chain:
                total = sum(open_st.line_ids.mapped('amount'))
                if open_st.id == st.id and getattr(open_st, 'prs_balance_start_manual', False):
                    new_start = float(open_st.balance_start or 0.0)
                else:
                    new_start = last_end

                new_end = new_start + total
                vals = {'balance_end_real': new_end}
                if open_st.id != st.id or not getattr(open_st, 'prs_balance_start_manual', False):
                    vals['balance_start'] = new_start

                open_st.with_context(
                    prs_skip_balance_recompute=True,
                    check_move_validity=False,
                ).write(vals)

                self.env.cr.execute(
                    "UPDATE account_bank_statement SET balance_end = %s WHERE id = %s",
                    (new_end, open_st.id)
                )
                open_st.invalidate_recordset(['balance_end'])
                last_end = new_end

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Saldos recalculados',
                'message': (
                    'El balance inicial y final del Estado de Cuenta y los '
                    'siguientes fueron recalculados correctamente.'
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model_create_multi
    def create(self, vals_list):
        statements = super().create(vals_list)
        try:
            statements._prs_recompute_balances()
        except Exception:
            _logger.warning("PRS: error al recalcular saldos tras crear estados de cuenta", exc_info=True)
        return statements

    def write(self, vals):
        # Bloqueo: no permitir modificar un Estado de Cuenta CERRADO (excepto su propio estado y chatter).
        if not self.env.context.get('prs_allow_closed_statement_write'):
            closed = self.filtered(lambda s: s.prs_state == 'closed')
            if closed:
                allowed = {
                    'prs_state',
                    'message_follower_ids', 'message_ids',
                    'activity_ids', 'activity_state', 'activity_user_id', 'activity_type_id', 'activity_date_deadline',
                }
                if set(vals) - allowed:
                    raise ValidationError("No se puede modificar un Estado de Cuenta CERRADO.")
        # Si el diario está configurado para saldo automático:
        # - NUNCA se permite editar el saldo final manualmente.
        # - El saldo inicial SOLO se permite editar en el PRIMER estado de cuenta ABIERTO del diario.
        if not self.env.context.get('prs_skip_balance_recompute') and any(getattr(s.journal_id, 'prs_auto_statement_balance', False) for s in self):
            if 'balance_start' in vals:
                not_allowed = self.filtered(
                    lambda s: getattr(s.journal_id, 'prs_auto_statement_balance', False)
                    and getattr(s, 'prs_state', 'open') == 'open'
                    and not s._prs_is_first_open_auto_runtime()
                )
                if not_allowed:
                    raise ValidationError(
                        "Solo se puede modificar el Saldo inicial en el PRIMER Estado de Cuenta ABIERTO del diario."
                    )
                # Marcamos que el saldo inicial fue definido manualmente.
                vals = dict(vals)
                vals['prs_balance_start_manual'] = True

        res = super().write(vals)
        if not self.env.context.get('prs_skip_balance_recompute'):
            try:
                # Recalcular en cadena: cambios en un estado pueden afectar
                # el saldo inicial/final de los siguientes estados del mismo diario.
                self._prs_recompute_balances(start_from=min(self, key=lambda s: (s.date or fields.Date.today(), s.id)))
            except Exception:
                _logger.warning("PRS: error al recalcular saldos en cadena tras modificar estado de cuenta %s", self.ids, exc_info=True)
        return res

    def _prs_recompute_balances(self, start_from=None):
        """Recalcula saldo inicial y final en cadena.

        Regla:
        - Si el diario tiene `prs_auto_statement_balance` activo y el estado está ABIERTO,
          entonces:
            * balance_start = balance_final del estado anterior (mismo diario)
            * balance_end_real = balance_start + suma(importes de line_ids)

        Importante: si cambia un estado (o sus líneas), los estados siguientes del mismo
        diario deben recalcularse también.
        """
        if self.env.context.get('prs_skip_balance_recompute'):
            return

        # Trabajamos por diario para garantizar el encadenamiento.
        statements = self.filtered(lambda s: getattr(s, 'prs_state', 'open') == 'open' and getattr(s.journal_id, 'prs_auto_statement_balance', False))
        if not statements:
            return

        # Si nos pasaron un start_from, recalculamos desde ahí en adelante (mismo diario).
        if start_from and start_from.journal_id:
            journals = start_from.journal_id
            start_key = (start_from.date or fields.Date.today(), start_from.id)
        else:
            journals = statements.mapped('journal_id')
            start_key = None

        Statement = self.env['account.bank.statement']

        def _get_end_value(st):
            """Devuelve el saldo final del estado (end_real o end)."""
            if 'balance_end_real' in st._fields and st.balance_end_real is not False:
                return st.balance_end_real or 0.0
            if 'balance_end' in st._fields and st.balance_end is not False:
                return st.balance_end or 0.0
            return 0.0

        for journal in journals:
            # Primer estado ABIERTO del diario (solo relevante si el diario tiene el check activo)
            first_open = False
            if getattr(journal, 'prs_auto_statement_balance', False):
                first_open = Statement.search([
                    ('journal_id', '=', journal.id),
                    ('prs_state', '=', 'open'),
                ], order='date asc, id asc', limit=1)
            first_open_id = first_open.id if first_open else False

            # Si nos pasaron un start_key, evitamos traer todos los estados históricos:
            # obtenemos solo el anterior como base y los que van desde start_key en adelante.
            if start_key:
                start_date, start_id = start_key
                prev_st = Statement.search([
                    ('journal_id', '=', journal.id),
                    '|',
                    ('date', '<', start_date),
                    '&', ('date', '=', start_date), ('id', '<', start_id),
                ], order='date desc, id desc', limit=1)
                last_end = _get_end_value(prev_st) if prev_st else 0.0
                st_iter = Statement.search([
                    ('journal_id', '=', journal.id),
                    '|',
                    ('date', '>', start_date),
                    '&', ('date', '=', start_date), ('id', '>=', start_id),
                ], order='date asc, id asc')
            else:
                last_end = 0.0
                st_iter = Statement.search(
                    [('journal_id', '=', journal.id)], order='date asc, id asc'
                )

            if not st_iter:
                continue

            # Encadenado: recorremos TODOS los estados en orden, pero solo recalculamos
            # los ABIERTOS (los cerrados / no auto quedan como base fija).
            for st in st_iter:
                # Si está cerrado o el check del diario no está activo, lo tratamos como fijo.
                if getattr(st, 'prs_state', 'open') != 'open' or not getattr(st.journal_id, 'prs_auto_statement_balance', False):
                    last_end = _get_end_value(st)
                    continue

                only_reconciled = bool(getattr(st.journal_id, 'prs_only_reconciled_statements', False))

                # ABIERTO + auto: calculamos
                is_first_open = bool(first_open_id and st.id == first_open_id)
                if is_first_open and getattr(st, 'prs_balance_start_manual', False):
                    start = float(st.balance_start or 0.0)
                    # balance_end_real: solo reconciliados si el flag está activo
                    total_for_end = st._prs_get_lines_total(only_reconciled=only_reconciled) if 'line_ids' in st._fields else 0.0
                    end = start + total_for_end
                    vals = {}
                    # No tocamos balance_start cuando es manual
                    if 'balance_end_real' in st._fields:
                        vals['balance_end_real'] = end
                    # last_end encadena con el total REAL para que running_balance sea correcto
                    total_real = st._prs_get_lines_total(only_reconciled=False) if 'line_ids' in st._fields else 0.0
                    last_end_next = start + total_real
                else:
                    start = last_end
                    # balance_end_real: solo reconciliados si el flag está activo
                    total_for_end = st._prs_get_lines_total(only_reconciled=only_reconciled) if 'line_ids' in st._fields else 0.0
                    end = start + total_for_end
                    vals = {}
                    if 'balance_start' in st._fields:
                        vals['balance_start'] = start
                    if 'balance_end_real' in st._fields:
                        vals['balance_end_real'] = end
                    # Si tenía marcado manual pero ya no es el primer abierto, lo reseteamos.
                    if getattr(st, 'prs_balance_start_manual', False) and not is_first_open:
                        vals['prs_balance_start_manual'] = False
                    # last_end encadena con el total REAL (todas las líneas) para que
                    # el balance_start del siguiente estado sea correcto y Odoo pueda
                    # calcular el running_balance individual de cada línea sin afectarse
                    # por el filtro de solo-conciliados.
                    total_real = st._prs_get_lines_total(only_reconciled=False) if 'line_ids' in st._fields else 0.0
                    last_end_next = start + total_real

                if vals:
                    st.with_context(prs_skip_balance_recompute=True, check_move_validity=False).write(vals)

                # El encadenamiento para el SIGUIENTE estado usa el total real
                # (no filtrado por reconciliación) para que balance_start sea correcto.
                last_end = last_end_next

                # Recalcular diferencias si aplica
                try:
                    if hasattr(st, '_compute_difference'):
                        st._compute_difference()
                except Exception:
                    _logger.warning("PRS: error al recalcular diferencia en estado %s", st.id, exc_info=True)


    def unlink(self):
        # Bloqueo: no permitir eliminar un Estado de Cuenta CERRADO.
        if self.filtered(lambda s: getattr(s, 'prs_state', 'open') == 'closed') and not self.env.context.get('prs_allow_closed_statement_write'):
            raise ValidationError("No se puede eliminar un Estado de Cuenta CERRADO.")

        if prs_is_pos(self.env):
            return super().unlink()
        if self.env.context.get("allow_delete_from_payment"):
            return super().unlink()

        Payment = self.env["account.payment"]
        for st in self:
            has_payment_lines = False
            for line in st.line_ids:
                if "payment_id" in line._fields and line.payment_id:
                    has_payment_lines = True
                    break
                refs = []
                if line.payment_ref:
                    refs.append(line.payment_ref)
                if getattr(line, "name", False):
                    refs.append(line.name)
                if refs:
                    conds = []
                    if "memo" in Payment._fields:
                        conds.append(("memo", "in", refs))
                    if "name" in Payment._fields:
                        conds.append(("name", "in", refs))
                    if "communication" in Payment._fields:
                        conds.append(("communication", "in", refs))
                    if conds:
                        domain = conds[0]
                        for c in conds[1:]:
                            domain = ["|", domain, c]
                        if Payment.search(domain, limit=1):
                            has_payment_lines = True
                            break

            auto_types = getattr(Payment, '_PRS_AUTO_EXTRACT_TYPES', ('cash', 'bank', 'credit_card'))
            journal = st.journal_id

            # Si el diario tiene activo el flag de borrado libre, no bloqueamos.
            # El pago NO se borra — solo el estado de cuenta.
            if getattr(journal, 'prs_allow_delete_statement_with_payments', False):
                continue

            if has_payment_lines and (journal and journal.type in auto_types and getattr(journal, 'auto_extract_enabled', False)):
                raise ValidationError(
                    "Este estado de cuenta se creó desde un pago.\n"
                    "Bórralo/restablécelo desde el pago asociado, "
                    "o activá 'Permitir borrar estados con pagos' en la configuración del diario."
                )
        return super().unlink()


# =====================================================================
# ACCOUNT MOVE LINE (CORREGIDO)
# =====================================================================
class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _prs_recompute_linked_statement_balances(self):
        """Recalcula los estados de cuenta afectados por conciliación/desconciliación.

        En varios flujos de conciliación Odoo crea/modifica/elimina `account.move.line`
        ligados a `statement_line_id` sin escribir directamente sobre la línea de extracto.
        Si no recalculamos acá, el saldo del estado y los reportes quedan desactualizados
        hasta refrescar manualmente.
        """
        try:
            statements = self.mapped('statement_line_id.statement_id').filtered(
                lambda s: getattr(s.journal_id, 'prs_auto_statement_balance', False)
            )
            if statements:
                statements._prs_recompute_balances()
        except Exception:
            pass

    @api.model_create_multi
    def create(self, vals_list):
        """ACEPTA dict o lista. Manejo correcto para POS y conciliación."""

        # 🔥 Si Odoo trae un dict, lo convertimos en lista
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        env = self.env
        pre_state = {}

        # Guardamos estado previo
        for vals in vals_list:
            st_line_id = vals.get("statement_line_id")
            if st_line_id:
                st = env["account.bank.statement.line"].browse(st_line_id)
                pre_state[st.id] = bool(getattr(st, "is_reconciled", False))

        # Creamos los apuntes
        records = super().create(vals_list)

        # Revisamos líneas de extracto afectadas
        st_to_check = {}
        for aml in records:
            st = getattr(aml, "statement_line_id", False)
            if st:
                st_to_check[st.id] = st

        if st_to_check:
            lines_now = env["account.bank.statement.line"].browse(list(st_to_check.keys()))
            lines_to_validate = lines_now.filtered(
                lambda l: (not pre_state.get(l.id, False)) and bool(getattr(l, "is_reconciled", False))
            )
            if lines_to_validate:
                lines_to_validate._validate_related_payments_after_reconcile()
            records._prs_recompute_linked_statement_balances()

        return records

    def write(self, vals):
        linked_before = self.filtered(lambda l: getattr(l, 'statement_line_id', False))
        res = super().write(vals)
        linked_after = self.filtered(lambda l: getattr(l, 'statement_line_id', False))
        to_recompute = linked_before | linked_after
        if to_recompute:
            to_recompute._prs_recompute_linked_statement_balances()
        return res

    def unlink(self):
        linked = self.filtered(lambda l: getattr(l, 'statement_line_id', False))
        statements = linked.mapped('statement_line_id.statement_id')
        res = super().unlink()
        try:
            if statements:
                statements._prs_recompute_balances()
        except Exception:
            pass
        return res
