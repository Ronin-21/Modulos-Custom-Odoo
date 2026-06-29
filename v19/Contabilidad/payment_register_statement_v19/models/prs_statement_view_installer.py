# -*- coding: utf-8 -*-
import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class PRSStatementViewInstaller(models.AbstractModel):
    _name = "prs.statement.view.installer"
    _description = "PRS - Bank Statement View Installer"

    @api.model
    def setup_bank_statement_view(self):
        """Create/Update inherited form views for account.bank.statement.

        Problema real en tu DB:
        - Hay más de un formulario (varias vistas raíz) para account.bank.statement.
        - Algunas vistas NO tienen <header>.
        - Una vista legacy del módulo aún intentaba hacer xpath //header y rompía.

        Solución:
        1) Desactivar cualquier vista heredada *nuestra* que intente usar //header.
        2) Parchear TODAS las vistas raíz (inherit_id = False) del modelo,
           creando una vista heredada por cada raíz, insertando un <header>
           antes de <sheet> (o dentro de <form> si no hay sheet).

        Así el botón aparece en el formulario que uses (Tablero/Conciliación bancaria,
        menú clásico, etc.) y no depende de XMLIDs externos.
        """
        View = self.env['ir.ui.view'].sudo()

        # ------------------------------------------------------------
        # 0) Desactivar vistas legacy que rompen por //header
        # ------------------------------------------------------------
        try:
            legacy = View.search([
                ('model', '=', 'account.bank.statement'),
                ('type', '=', 'form'),
                ('active', '=', True),
                # Solo desactivamos si claramente es nuestra vista (contiene nuestros botones/campo)
                '|',
                    ('arch_db', 'ilike', 'action_prs_close_statement'),
                    ('arch_db', 'ilike', 'prs_state'),
            ])

            # De esas, desactivamos únicamente las que:
            # - usen xpath hacia //header (rompía en varias bases), o
            # - usen la notación con puntos `journal_id.prs_auto_statement_balance` en expresiones
            #   (en algunos despliegues deja los campos siempre en readonly aunque el check esté apagado).
            legacy_to_disable = legacy.filtered(
                lambda v: ('//header' in (v.arch_db or '')) or ('journal_id.prs_auto_statement_balance' in (v.arch_db or ''))
            )
            if legacy_to_disable:
                legacy_to_disable.write({'active': False})
        except Exception as e:
            _logger.warning('PRS cleanup failed while disabling legacy bank statement views: %s', e)

        # ------------------------------------------------------------
        # 1) Parchear TODAS las vistas raíz (inherit_id=False)
        # ------------------------------------------------------------
        root_views = View.search([
            ('model', '=', 'account.bank.statement'),
            ('type', '=', 'form'),
            ('active', '=', True),
            ('inherit_id', '=', False),
        ], order='priority desc, id desc')

        if not root_views:
            _logger.warning('PRS: No root form view found for account.bank.statement; skipping view setup.')
            return True

        def build_arch(base_arch: str) -> str:
            base_arch = base_arch or ''
            has_sheet = '<sheet' in base_arch

            # Insertamos un header estándar para que los botones aparezcan como en Odoo.
            # No usamos xpath //header (porque puede no existir).
            if has_sheet:
                header_inject = """<xpath expr="//sheet" position="before">
                <header>
                    <button name="action_prs_close_statement" type="object" string="Cerrar Estado de cuenta" class="btn-primary" invisible="prs_state == 'closed'"/>
                    <button name="action_prs_reopen_statement" type="object" string="Reabrir Estado de cuenta" class="btn-secondary" groups="account.group_account_manager" invisible="prs_state == 'open'"/>
                    <button name="action_prs_recompute_balances" type="object" string="Recalcular saldos" class="btn-secondary" invisible="prs_state == 'closed'"/>
                    <field name="prs_state" widget="statusbar" statusbar_visible="open,closed"/>
                    <field name="prs_auto_statement_balance_active" invisible="1"/>
                    <field name="prs_is_first_open_auto" invisible="1"/>
                </header>
            </xpath>
"""
            else:
                header_inject = """<xpath expr="//form" position="inside">
                <header>
                    <button name="action_prs_close_statement" type="object" string="Cerrar Estado de cuenta" class="btn-primary" invisible="prs_state == 'closed'"/>
                    <button name="action_prs_reopen_statement" type="object" string="Reabrir Estado de cuenta" class="btn-secondary" groups="account.group_account_manager" invisible="prs_state == 'open'"/>
                    <button name="action_prs_recompute_balances" type="object" string="Recalcular saldos" class="btn-secondary" invisible="prs_state == 'closed'"/>
                    <field name="prs_state" widget="statusbar" statusbar_visible="open,closed"/>
                    <field name="prs_auto_statement_balance_active" invisible="1"/>
                    <field name="prs_is_first_open_auto" invisible="1"/>
                </header>
            </xpath>
"""

            # Readonly visual (solo si los campos están en el arch base, así evitamos errores de xpath)
            pieces = [header_inject]

            if 'name="line_ids"' in base_arch or "name='line_ids'" in base_arch:
                pieces.append("""<xpath expr="//field[@name='line_ids']" position="attributes">
                    <attribute name="readonly">prs_state == 'closed'</attribute>
                </xpath>
""")

            if 'name="balance_start"' in base_arch or "name='balance_start'" in base_arch:
                pieces.append("""<xpath expr="//field[@name='balance_start']" position="attributes">
                    <attribute name="readonly">prs_state == 'closed' or (prs_auto_statement_balance_active and not prs_is_first_open_auto)</attribute>
                </xpath>
""")

            # En algunos despliegues el saldo final puede ser balance_end_real o balance_end
            if 'name="balance_end_real"' in base_arch or "name='balance_end_real'" in base_arch:
                pieces.append("""<xpath expr="//field[@name='balance_end_real']" position="attributes">
                    <attribute name="readonly">prs_state == 'closed' or prs_auto_statement_balance_active</attribute>
                </xpath>
""")
            elif 'name="balance_end"' in base_arch or "name='balance_end'" in base_arch:
                pieces.append("""<xpath expr="//field[@name='balance_end']" position="attributes">
                    <attribute name="readonly">prs_state == 'closed' or prs_auto_statement_balance_active</attribute>
                </xpath>
""")

            arch_db = '<data>\n' + ''.join(pieces) + '</data>'
            return arch_db

        created = 0
        updated = 0

        for base_view in root_views:
            arch_db = build_arch(base_view.arch_db or '')

            # Vista heredada única por raíz
            view_name = f"account.bank.statement.form.prs.state (dyn root {base_view.id})"
            prs_view = View.search([
                ('model', '=', 'account.bank.statement'),
                ('type', '=', 'form'),
                ('inherit_id', '=', base_view.id),
                ('name', '=', view_name),
            ], limit=1)

            vals = {
                'name': view_name,
                'type': 'form',
                'model': 'account.bank.statement',
                'inherit_id': base_view.id,
                'priority': 99,
                'active': True,
                'arch_db': arch_db,
            }

            if prs_view:
                prs_view.write(vals)
                updated += 1
            else:
                View.create(vals)
                created += 1

        _logger.info('PRS: bank statement views patched. roots=%s created=%s updated=%s', len(root_views), created, updated)
        self._prs_patch_statement_actions()
        return True

    @api.model
    def _prs_patch_statement_actions(self):
        """Agrega 'form' al view_mode de todas las acciones de account.bank.statement.

        En Odoo 19, la accion de Cajas Registradoras puede tener view_mode='list' solamente.
        Esto impide abrir el formulario al hacer clic en una fila.
        Buscamos todas las acciones del modelo por busqueda directa (no por XML ID,
        que puede variar entre instalaciones) y agregamos 'form' si no esta presente.
        """
        Action = self.env['ir.actions.act_window'].sudo()
        patched_ids = set()

        # 1) Intentar por XML IDs conocidos
        known_xmlids = [
            'account.action_bank_statement_tree',
            'account.action_bank_statement_form',
            'account.action_account_bank_statement_tree',
        ]
        for xmlid in known_xmlids:
            try:
                action = self.env.ref(xmlid, raise_if_not_found=False)
                if action and action.res_model == 'account.bank.statement':
                    if 'form' not in (action.view_mode or ''):
                        action.write({'view_mode': (action.view_mode or 'list') + ',form'})
                        _logger.info('PRS: patched action %s -> view_mode=%s', xmlid, action.view_mode)
                    patched_ids.add(action.id)
            except Exception as e:
                _logger.warning('PRS: could not patch action %s: %s', xmlid, e)

        # 2) Fallback: cualquier accion sobre el modelo sin form view
        try:
            all_actions = Action.search([
                ('res_model', '=', 'account.bank.statement'),
                ('type', '=', 'ir.actions.act_window'),
            ])
            for action in all_actions:
                if action.id in patched_ids:
                    continue
                if 'form' not in (action.view_mode or ''):
                    old_mode = action.view_mode or 'list'
                    action.write({'view_mode': old_mode + ',form'})
                    _logger.info(
                        'PRS: patched action id=%s "%s": %s -> %s',
                        action.id, action.name, old_mode, action.view_mode,
                    )
        except Exception as e:
            _logger.warning('PRS: fallback action patch failed: %s', e)
