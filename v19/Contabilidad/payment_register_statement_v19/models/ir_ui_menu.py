# -*- coding: utf-8 -*-
import json

from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _prs_fix_accounting_menu_labels(self, *args):
        """Force the Accounting app label without breaking upgrades.

        Some Odoo 18 databases store translated menu names as JSONB and some
        still use text + translations.  Also, Spanish variants can be es_AR,
        es_ES, es_419, etc.  This method patches all active languages and never
        raises, because menu labelling must not block the registry.
        """
        menu = self.env.ref('account.menu_finance', raise_if_not_found=False)
        if not menu:
            return True

        menu.sudo().write({'active': True})
        languages = set(self.env['res.lang'].sudo().search([('active', '=', True)]).mapped('code'))
        languages.update(['en_US', 'es_AR', 'es_ES', 'es_419'])
        labels = {}
        for lang in languages:
            if (lang or '').startswith('es'):
                labels[lang] = 'Contabilidad'
            else:
                labels[lang] = 'Accounting'
        labels.setdefault('en_US', 'Accounting')

        # Try ORM writes first so Odoo updates its translation caches normally.
        for lang, value in labels.items():
            try:
                menu.with_context(lang=lang).sudo().write({'name': value})
            except Exception:
                pass

        try:
            self.env.cr.execute("""
                SELECT data_type, udt_name
                  FROM information_schema.columns
                 WHERE table_name = 'ir_ui_menu'
                   AND column_name = 'name'
                 LIMIT 1
            """)
            row = self.env.cr.fetchone() or ('', '')
            data_type = row[0] or ''
            udt_name = row[1] or ''
            if data_type == 'jsonb' or udt_name == 'jsonb':
                self.env.cr.execute("""
                    UPDATE ir_ui_menu
                       SET name = COALESCE(name, '{}'::jsonb) || %s::jsonb,
                           active = TRUE
                     WHERE id = %s
                """, [json.dumps(labels), menu.id])
            elif data_type == 'json' or udt_name == 'json':
                # json has no || merge operator. Cast to jsonb, merge, cast back.
                self.env.cr.execute("""
                    UPDATE ir_ui_menu
                       SET name = (COALESCE(name::jsonb, '{}'::jsonb) || %s::jsonb)::json,
                           active = TRUE
                     WHERE id = %s
                """, [json.dumps(labels), menu.id])
            else:
                self.env.cr.execute(
                    "UPDATE ir_ui_menu SET name = %s, active = TRUE WHERE id = %s",
                    ['Contabilidad', menu.id],
                )
        except Exception:
            pass

        # NOTE: ir_translation table removed in Odoo 16+. No-op here.
        try:
            self.env['ir.ui.menu'].clear_caches()
        except Exception:
            pass
        return True
    @api.model
    def _prs_adjust_money_flow_menu_parent(self, *args):
        """Place PRS under the real Accounting app root.

        Keep the manifest dependencies unchanged: accountant/account_accountant may
        or may not be installed, so optional XML IDs are resolved here.  The menu
        itself must not be restricted by the technical activation group, because
        otherwise no user receives it until after a settings save.  The feature
        logic remains controlled by Ajustes > Contabilidad > Flujo de Pagos.
        """
        root = self.env.ref('payment_register_statement_v19.menu_prs_money_flow_root', raise_if_not_found=False)
        if not root:
            return True

        # In Odoo 19 there are two common accounting app layouts:
        # - accountant module: accountant.menu_accounting is the top Accounting app
        # - account_accountant module: account.menu_finance is renamed/reactivated
        # Some databases also move account.menu_finance_entries below a custom
        # Accounting root, so use that parent as a final fallback.
        candidates = [
            self.env.ref('accountant.menu_accounting', raise_if_not_found=False),
            self.env.ref('account.menu_finance', raise_if_not_found=False),
        ]
        entries_menu = self.env.ref('account.menu_finance_entries', raise_if_not_found=False)
        if entries_menu and entries_menu.parent_id:
            candidates.append(entries_menu.parent_id)

        target = False
        for candidate in candidates:
            if candidate and candidate.active:
                target = candidate
                break
        if not target:
            target = next((candidate for candidate in candidates if candidate), False)

        sequence = 14
        if target:
            config_menu = self.env.ref('account.menu_finance_configuration', raise_if_not_found=False)
            if config_menu and config_menu.parent_id == target:
                sequence = max((config_menu.sequence or 15) - 1, 1)
        vals = {
            'sequence': sequence,
            'active': True,
            'group_ids': [(5, 0, 0)],
        }
        if target:
            vals['parent_id'] = target.id
            if not target.active:
                target.sudo().write({'active': True})
            if target == self.env.ref('account.menu_finance', raise_if_not_found=False):
                try:
                    self._prs_fix_accounting_menu_labels()
                except Exception:
                    pass
        root.sudo().write(vals)

        # Ensure the obsolete children stay hidden; the root menu opens the single
        # supported action with list/pivot/calendar/graph/form views.
        for xmlid in (
            'payment_register_statement_v19.menu_prs_money_flow',
            'payment_register_statement_v19.menu_prs_money_flow_calendar_grouped',
            'payment_register_statement_v19.menu_prs_money_flow_grid',
        ):
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                menu.sudo().write({'active': False, 'group_ids': [(5, 0, 0)]})

        try:
            self.env['ir.ui.menu'].clear_caches()
        except Exception:
            pass
        return True

    @api.model
    def _prs_money_flow_menu_ids(self):
        xmlids = (
            'payment_register_statement_v19.menu_prs_money_flow_root',
            'payment_register_statement_v19.menu_prs_money_flow',
            'payment_register_statement_v19.menu_prs_money_flow_calendar_grouped',
            'payment_register_statement_v19.menu_prs_money_flow_grid',
        )
        ids = []
        for xmlid in xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                ids.append(menu.id)
                try:
                    ids.extend(self.search([('id', 'child_of', menu.id)]).ids)
                except Exception:
                    pass
        return list(set(ids))

    @api.model
    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        try:
            res_ids = list(res or [])
        except Exception:
            res_ids = []
        try:
            enabled = bool(self.env.company.prs_money_flow_enabled)
        except Exception:
            enabled = False
        if not enabled:
            res_ids.extend(self._prs_money_flow_menu_ids())
        return list(set(res_ids))

