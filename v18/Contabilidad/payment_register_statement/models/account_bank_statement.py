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
            # saldos (_prs_recompute_balances solo procesa line_ids de un estado).
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
                pass

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

        prev_unreconciled = {l.id: not bool(getattr(l, "is_reconciled", False)) for l in self}
        res = super().write(vals)
        if vals.get("is_reconciled"):
            lines = self.filtered(lambda l: prev_unreconciled.get(l.id) and getattr(l, "is_reconciled", False))
            if lines:
                lines._validate_related_payments_after_reconcile()
        # Recalcular saldos automáticos si aplica
        try:
            self.mapped('statement_id')._prs_recompute_balances()
        except Exception:
            pass

        return res

    def _validate_related_payments_after_reconcile(self):
        Payment = self.env["account.payment"]
        for line in self:
            # Solo aplica cuando el diario tiene activada la opción
            # "Crear extractos automáticos".
            journal = (line.statement_id.journal_id if line.statement_id else line.journal_id)
            auto_types = getattr(Payment, '_PRS_AUTO_EXTRACT_TYPES', ('cash', 'bank', 'credit_card'))
            if not (journal and journal.type in auto_types and getattr(journal, 'auto_extract_enabled', False)):
                continue
            if not getattr(line, "is_reconciled", False):
                continue

            # Solo usamos el enlace directo payment_id (PRS siempre lo asigna).
            # Eliminamos las búsquedas por referencia/monto: son demasiado riesgosas
            # porque pueden matchear pagos incorrectos con el mismo importe.
            if "payment_id" not in line._fields or not line.payment_id:
                continue
            payments = line.payment_id

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
            # Solo bloqueamos si hay un payment_id directo (link explícito PRS).
            if "payment_id" not in line._fields or not line.payment_id:
                continue
            journal = (line.statement_id.journal_id if line.statement_id else line.journal_id)
            auto_types = getattr(Payment, '_PRS_AUTO_EXTRACT_TYPES', ('cash', 'bank', 'credit_card'))
            if journal and journal.type in auto_types and getattr(journal, 'auto_extract_enabled', False):
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

    def _compute_balance_end(self):
        """Override: lee balance_start SIEMPRE desde la DB para evitar valores cacheados.

        Causa raiz del bug: cuando PRS actualiza balance_start via write() con
        check_move_validity=False, el ORM de Odoo cachea el valor VIEJO en memoria.
        Luego, cuando algo dispara _compute_balance_end (ej: toggle del flag del diario),
        Odoo usa el cache y escribe un balance_end incorrecto, causando el aviso naranja
        y el color rojo en Cajas Registradoras.

        Fix: leer balance_start directo de la DB antes de cada calculo.
        """
        if not self:
            return
        # Leer balance_start fresco de la DB para todos los statements del batch
        ids = tuple(self.ids)
        if ids:
            self.env.cr.execute(
                "SELECT id, balance_start FROM account_bank_statement WHERE id IN %s",
                (ids,)
            )
            db_starts = {row[0]: row[1] for row in self.env.cr.fetchall()}
        else:
            db_starts = {}

        for statement in self:
            # db_starts.get() puede retornar None si balance_start es NULL en DB
            # (statements recién creados o migrados sin balance_start).
            # Usamos `or 0.0` para garantizar que sea siempre un float.
            db_start = db_starts.get(statement.id) or 0.0
            total = sum(statement.line_ids.mapped('amount'))
            statement.balance_end = db_start + total


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

    def _prs_get_lines_total(self, only_reconciled=None):
        """Suma los importes de las líneas del estado.

        IMPORTANTE: este método solo se usa para mostrar datos en el sidebar de
        conciliación y en reportes. El cálculo de balance_end_real almacenado
        SIEMPRE usa la suma de todas las líneas (ignorando only_reconciled) para
        que Odoo no muestre el aviso "balance en ejecución no coincide".

        Si only_reconciled=True (o el diario tiene prs_only_reconciled_statements),
        solo suma las líneas ya conciliadas.
        Si only_reconciled=False o None sin flag activo, suma todas las líneas.
        """
        self.ensure_one()
        if only_reconciled is None:
            only_reconciled = bool(
                getattr(self.journal_id, 'prs_only_reconciled_statements', False)
            )
        if not only_reconciled:
            return sum(self.line_ids.mapped('amount'))
        return sum(
            line.amount
            for line in self.line_ids
            if self._prs_should_count_line_in_balance(line)
        )

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
            # Nuevo estado sin id aún (wizard de creación).
            # Incluir también estados de la MISMA fecha — el nuevo tendrá
            # un id mayor que los existentes, así que tomamos todos los
            # del mismo diario con date <= self.date como candidatos.
            prev_domain = [
                ('journal_id', '=', self.journal_id.id),
                ('date', '<=', self.date or fields.Date.today()),
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

        # balance_end_real: siempre suma TODAS las líneas (consistente con el almacenado).
        # El flag prs_only_reconciled_statements solo afecta la vista del sidebar.
        total = sum(self.line_ids.mapped('amount'))

        self.balance_start = start
        if 'balance_end_real' in self._fields:
            self.balance_end_real = start + total


    def action_prs_close_statement(self):
        # Antes de cerrar, si el diario tiene saldo automático, dejamos los saldos al día.
        try:
            self._prs_recompute_balances()
        except Exception:
            pass
        self.write({'prs_state': 'closed'})
        return True

    def action_prs_reopen_statement(self):
        # Reabrir solo por Administrador de Contabilidad.
        if not self.env.user.has_group('account.group_account_manager'):
            raise ValidationError("No tiene permisos para reabrir un Estado de Cuenta.")
        self.write({'prs_state': 'open'})
        return True

    def create(self, vals_list):
        statements = super().create(vals_list)
        try:
            statements._prs_recompute_balances()
        except Exception:
            pass
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
            if any(k in vals for k in ('balance_end_real', 'balance_end')):
                raise ValidationError("Este diario tiene cálculo automático de saldos. No puede modificar el saldo final manualmente.")
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
                pass
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
            st_all = Statement.search(
                [('journal_id', '=', journal.id)],
                order='date asc, id asc'
            )
            if not st_all:
                continue

            # ── Determinar punto de arranque y saldo base ──────────────────
            # Path unificado: tanto con start_from como sin él usamos el mismo
            # mecanismo. La diferencia es solo qué statements iteramos.
            if start_key:
                # Con start_from: arrancamos desde ese estado.
                # Saldo base = balance_end_real del estado inmediatamente anterior.
                prev_st = st_all.filtered(
                    lambda s: (s.date or fields.Date.today(), s.id) < start_key
                )
                last_end = _get_end_value(prev_st[-1]) if prev_st else 0.0
                st_iter = st_all.filtered(
                    lambda s: (s.date or fields.Date.today(), s.id) >= start_key
                    and getattr(s, 'prs_state', 'open') == 'open'
                )
            else:
                # Sin start_from: arrancamos desde el primer estado abierto.
                # Ancla = balance_end_real del último estado CERRADO (historial inmutable).
                closed = st_all.filtered(lambda s: getattr(s, 'prs_state', 'open') == 'closed')
                last_end = _get_end_value(closed[-1]) if closed else 0.0
                st_iter = st_all.filtered(lambda s: getattr(s, 'prs_state', 'open') == 'open')

            if not st_iter:
                continue

            # Primer estado ABIERTO del diario (para respetar saldo inicial manual)
            first_open_id = st_iter[0].id if st_iter else False

            # ── Encadenamiento ─────────────────────────────────────────────
            for st in st_iter:
                # Suma directa de todas las líneas.
                # SIEMPRE usamos todas (no solo reconciliadas) para que
                # balance_end == balance_end_real y Odoo no muestre el aviso naranja.
                # El flag prs_only_reconciled_statements solo afecta reportes/sidebar.
                total = sum(st.line_ids.mapped('amount'))

                is_first = st.id == first_open_id
                if is_first and getattr(st, 'prs_balance_start_manual', False):
                    # Primer estado con saldo inicial manual: respetarlo.
                    start = float(st.balance_start or 0.0)
                    end = start + total
                    vals = {'balance_end_real': end}
                else:
                    start = last_end
                    end = start + total
                    vals = {'balance_start': start, 'balance_end_real': end}
                    if getattr(st, 'prs_balance_start_manual', False) and not is_first:
                        vals['prs_balance_start_manual'] = False

                st.with_context(
                    prs_skip_balance_recompute=True,
                    check_move_validity=False,
                ).write(vals)

                # Sincronizar balance_end (campo STORED de Odoo) via SQL.
                # Cuando PRS escribe con check_move_validity=False, el ORM de Odoo
                # a veces no dispara el recompute del stored field correctamente,
                # dejando balance_end con el valor viejo (causa el aviso naranja).
                try:
                    self.env.cr.execute(
                        "UPDATE account_bank_statement SET balance_end = %s WHERE id = %s",
                        (end, st.id)
                    )
                    st.invalidate_recordset(['balance_end'])
                except Exception as e:
                    _logger.warning(
                        "PRS: no se pudo sincronizar balance_end para statement %s: %s",
                        st.id, e
                    )

                last_end = end

                try:
                    if hasattr(st, '_compute_difference'):
                        st._compute_difference()
                except Exception:
                    pass


    def unlink(self):
        # Bloqueo: no permitir eliminar un Estado de Cuenta CERRADO.
        if self.filtered(lambda s: getattr(s, 'prs_state', 'open') == 'closed')                 and not self.env.context.get('prs_allow_closed_statement_write'):
            raise ValidationError("No se puede eliminar un Estado de Cuenta CERRADO.")

        if prs_is_pos(self.env):
            return super().unlink()
        if self.env.context.get("allow_delete_from_payment"):
            return super().unlink()

        Payment = self.env["account.payment"]
        for st in self:
            journal = st.journal_id

            # Si el diario tiene activo el flag de borrado libre, no bloqueamos.
            # El pago NO se borra — solo el estado de cuenta.
            if getattr(journal, 'prs_allow_delete_statement_with_payments', False):
                continue

            # Solo bloqueamos si alguna línea tiene payment_id directo (link explícito PRS).
            auto_types = getattr(Payment, '_PRS_AUTO_EXTRACT_TYPES', ('cash', 'bank', 'credit_card'))
            if journal and journal.type in auto_types and getattr(journal, 'auto_extract_enabled', False):
                has_payment_lines = (
                    "payment_id" in st.line_ids._fields
                    and any(l.payment_id for l in st.line_ids)
                )
                if has_payment_lines:
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
            statements = self.mapped('statement_line_id.statement_id')
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
        (linked_before | linked_after)._prs_recompute_linked_statement_balances()
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
