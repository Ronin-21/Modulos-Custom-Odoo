# -*- coding: utf-8 -*-
"""
stock_location_init_wizard.py
==============================
Wizard de inicialización manual de ``allowed_company_ids`` en ubicaciones.

Modos
-----
* **Con empresa (company_id)**: copia company_id → allowed_company_ids.
* **Sin empresa — asignar empresas**: asigna las empresas del campo
  ``fallback_company_ids`` a ubicaciones sin company_id.
* **Ambas**: ejecuta los dos pasos.

Filtro de ubicaciones
---------------------
Si se completa ``target_location_ids``, el wizard solo procesa esas
ubicaciones (independientemente del modo). Esto permite una asignación
quirúrgica: elegís exactamente qué ubicaciones tocar y qué empresas asignar.

Seguridad
---------
* No toca ubicaciones que ya tienen ``allowed_company_ids`` salvo que se
  active ``overwrite_existing``.
* Omite siempre las ubicaciones técnicas de Odoo.
* No modifica nada al instalar/actualizar el módulo.
"""

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_SKIP_USAGES = frozenset(['customer', 'supplier', 'inventory', 'production', 'view'])


class StockLocationInitWizard(models.TransientModel):
    _name = 'stock.location.init.wizard'
    _description = 'Inicializar Empresas Permitidas en Ubicaciones'

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------

    mode = fields.Selection(
        selection=[
            ('with_company',    'Solo ubicaciones que tienen empresa (company_id)'),
            ('without_company', 'Solo ubicaciones sin empresa (company_id vacío)'),
            ('both',            'Ambas'),
        ],
        string='Modo',
        required=True,
        default='without_company',
    )

    # Filtro manual de ubicaciones (opcional)
    target_location_ids = fields.Many2many(
        comodel_name='stock.location',
        relation='stock_location_init_wiz_loc_rel',
        column1='wizard_id',
        column2='location_id',
        string='Ubicaciones a procesar',
        domain=[
            ('usage', 'not in', ['customer', 'supplier', 'inventory', 'production', 'view']),
            ('scrap_location', '=', False),
        ],
        help=(
            'Opcional. Si se seleccionan ubicaciones aquí, el wizard procesa '
            'SOLO esas ubicaciones, ignorando el Modo.\n'
            'Si se deja vacío, el wizard procesa todas las que correspondan al Modo.'
        ),
    )

    fallback_company_ids = fields.Many2many(
        comodel_name='res.company',
        relation='stock_location_init_wiz_company_rel',
        column1='wizard_id',
        column2='company_id',
        string='Empresas a asignar',
        help=(
            'Empresas que se asignarán como "Empresas permitidas".\n'
            '• En modo "Sin empresa": se asignan a las ubicaciones sin company_id.\n'
            '• Si hay ubicaciones seleccionadas manualmente: se asignan a todas ellas '
            '(sobreescribe la lógica de company_id).\n'
            '• En modo "Con empresa" sin selección manual: se ignora este campo '
            '(se usa company_id de cada ubicación).'
        ),
    )

    overwrite_existing = fields.Boolean(
        string='Sobreescribir allowed_company_ids existentes',
        default=False,
        help='Si está marcado, reemplaza los allowed_company_ids ya configurados.',
    )

    include_scrap = fields.Boolean(
        string='Incluir ubicaciones de scrap',
        default=False,
    )

    # ------------------------------------------------------------------
    # Vista previa
    # ------------------------------------------------------------------

    preview_text = fields.Text(string='Vista previa', readonly=True)
    preview_count_total = fields.Integer(string='Ubicaciones a procesar', readonly=True)

    # ------------------------------------------------------------------
    # Onchange para actualizar vista previa automáticamente
    # ------------------------------------------------------------------

    @api.onchange('mode', 'target_location_ids', 'fallback_company_ids',
                  'overwrite_existing', 'include_scrap')
    def _onchange_params(self):
        self._compute_preview()

    # ------------------------------------------------------------------
    # Lógica de preview
    # ------------------------------------------------------------------

    def _compute_preview(self):
        locations = self._get_locations_to_process()
        lines = []

        if self.target_location_ids:
            lines.append('=== MODO: Ubicaciones seleccionadas manualmente (%d) ===' % len(locations))
            companies = self.fallback_company_ids.mapped('name') or ['(ninguna — completar campo Empresas a asignar)']
            lines.append('Empresas a asignar: %s' % ', '.join(companies))
        else:
            lines.append('=== MODO: %s (%d ubicaciones) ===' % (
                dict(self._fields['mode'].selection)[self.mode], len(locations)
            ))

        if not locations:
            lines.append('\n(ninguna ubicación a procesar con la configuración actual)')
        else:
            current_type = None
            for loc in locations:
                tipo = 'Con empresa: %s' % loc.company_id.name if loc.company_id else 'Sin empresa'
                if tipo != current_type:
                    current_type = tipo
                    lines.append('\n%s:' % tipo)
                emp_dest = self._get_companies_for_location(loc)
                emp_str = ', '.join(emp_dest.mapped('name')) if emp_dest else '(no se asignarán empresas)'
                lines.append('  • %s → [%s]' % (loc.complete_name, emp_str))

        if not self.overwrite_existing:
            lines.append(
                '\n⚠ Solo se procesan ubicaciones con allowed_company_ids vacío. '
                'Active "Sobreescribir" para incluir las ya configuradas.'
            )

        self.preview_text = '\n'.join(lines)
        self.preview_count_total = len(locations)

    def _get_companies_for_location(self, loc):
        """Retorna las empresas que se asignarían a esta ubicación."""
        if self.target_location_ids or self.mode == 'without_company':
            return self.fallback_company_ids
        if self.mode == 'with_company' and loc.company_id:
            return loc.company_id
        if self.mode == 'both':
            return loc.company_id if loc.company_id else self.fallback_company_ids
        return self.env['res.company']

    # ------------------------------------------------------------------
    # Obtener ubicaciones a procesar
    # ------------------------------------------------------------------

    def _base_domain(self):
        domain = [('usage', 'not in', list(_SKIP_USAGES))]
        if not self.include_scrap:
            domain.append(('scrap_location', '=', False))
        if not self.overwrite_existing:
            domain.append(('allowed_company_ids', '=', False))
        return domain

    def _get_locations_to_process(self):
        """Retorna las ubicaciones que serán procesadas."""
        # Modo manual: solo las seleccionadas
        if self.target_location_ids:
            locs = self.target_location_ids
            if not self.overwrite_existing:
                locs = locs.filtered(lambda l: not l.allowed_company_ids)
            return locs

        # Modo automático según 'mode'
        base = self._base_domain()
        if self.mode == 'with_company':
            return self.env['stock.location'].sudo().search(
                base + [('company_id', '!=', False)]
            )
        elif self.mode == 'without_company':
            return self.env['stock.location'].sudo().search(
                base + [('company_id', '=', False)]
            )
        else:  # both
            return self.env['stock.location'].sudo().search(base)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def action_preview(self):
        """Recalcula y muestra la vista previa."""
        self._compute_preview()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        """Aplica la inicialización."""
        locations = self._get_locations_to_process()

        if not locations:
            raise UserError(_('No hay ubicaciones a procesar con la configuración actual.'))

        # En modo manual con empresas: validar que se hayan seleccionado
        if self.target_location_ids and not self.fallback_company_ids:
            raise UserError(_(
                'Seleccionó ubicaciones manualmente pero no indicó las '
                '"Empresas a asignar". Complete ese campo antes de aplicar.'
            ))

        # En modo sin empresa (automático) sin empresas: advertir
        if not self.target_location_ids and self.mode in ('without_company', 'both'):
            without = locations.filtered(lambda l: not l.company_id)
            if without and not self.fallback_company_ids:
                raise UserError(_(
                    'Hay %d ubicaciones sin company_id pero no se indicaron '
                    '"Empresas a asignar". Complete ese campo o cambie el modo.'
                ) % len(without))

        count = 0
        for loc in locations:
            companies = self._get_companies_for_location(loc)
            if not companies:
                continue
            cmd = [(6, 0, companies.ids)] if self.overwrite_existing \
                else [(4, c) for c in companies.ids]
            loc.sudo().write({'allowed_company_ids': cmd})
            _logger.info(
                'InitWizard: %s → allowed_company_ids=%s',
                loc.complete_name, companies.mapped('name')
            )
            count += 1

        self._compute_preview()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Inicialización completada'),
                'message': _('%d ubicación(es) actualizada(s).') % count,
                'type': 'success',
                'sticky': False,
            },
        }
