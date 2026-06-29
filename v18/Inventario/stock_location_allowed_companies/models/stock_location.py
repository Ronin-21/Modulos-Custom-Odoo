# -*- coding: utf-8 -*-
"""
stock_location.py
=================
Extiende ``stock.location`` con el campo Many2many ``allowed_company_ids``
y la lógica de compatibilidad asociada.

Decisiones de diseño
--------------------
* ``allowed_company_ids`` vacío → sin restricción adicional (comportamiento
  transparente para ubicaciones no configuradas).
* ``company_id`` estándar de Odoo NO se modifica.
* La creación de nuevas ubicaciones inicializa ``allowed_company_ids`` con la
  empresa activa (o con ``company_id`` si está definido), pero solo si el
  campo no fue provisto explícitamente en los vals.
* Las ubicaciones "técnicas" de Odoo (clientes, proveedores, inventario,
  producción, scrap, retorno) quedan exentas de cualquier validación.
* No se modifica ninguna ubicación existente en la instalación/actualización.
"""

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# Usages que Odoo usa internamente y que nunca deben ser bloqueados
_TECHNICAL_USAGES = frozenset(['customer', 'supplier', 'inventory', 'production'])


class StockLocation(models.Model):
    _inherit = 'stock.location'

    # ------------------------------------------------------------------
    # Campos nuevos
    # ------------------------------------------------------------------

    allowed_company_ids = fields.Many2many(
        comodel_name='res.company',
        relation='stock_location_allowed_company_rel',
        column1='location_id',
        column2='company_id',
        string='Empresas permitidas',
        help=(
            'Empresas que pueden usar esta ubicación.\n'
            'Si está vacío, no se aplica restricción adicional a esta ubicación.\n'
            'Este campo es complementario al campo "Empresa" estándar de Odoo '
            '(company_id) y no lo reemplaza.'
        ),
    )

    allowed_company_count = fields.Integer(
        string='N° Empresas',
        compute='_compute_allowed_company_count',
        store=True,
        help='Cantidad de empresas con permiso explícito sobre esta ubicación.',
    )

    is_shared_location = fields.Boolean(
        string='Compartida',
        compute='_compute_is_shared_location',
        store=True,
        help=(
            'Verdadero cuando la ubicación no tiene empresa estándar (company_id vacío) '
            'y tiene más de una empresa permitida configurada.'
        ),
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends('allowed_company_ids')
    def _compute_allowed_company_count(self):
        for loc in self:
            loc.allowed_company_count = len(loc.allowed_company_ids)

    @api.depends('allowed_company_ids', 'company_id')
    def _compute_is_shared_location(self):
        for loc in self:
            loc.is_shared_location = (
                not loc.company_id
                and len(loc.allowed_company_ids) > 1
            )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def is_allowed_for_company(self, company):
        """
        Verifica si la ubicación es utilizable por la empresa indicada.

        :param company: ``res.company`` record o ``int`` (id de empresa).
        :return: ``True`` si la empresa puede usar la ubicación.

        Lógica:
        1. Ubicaciones técnicas de Odoo → siempre permitidas.
        2. ``allowed_company_ids`` vacío → sin restricción custom; se respeta
           solo ``company_id`` estándar.
        3. ``allowed_company_ids`` con valores → la empresa debe estar en la lista.
        """
        self.ensure_one()
        company_id = company if isinstance(company, int) else company.id

        if self._is_technical_location():
            return True

        if not self.allowed_company_ids:
            # Sin restricción custom → verificar company_id estándar
            if not self.company_id:
                return True
            return self.company_id.id == company_id

        return company_id in self.allowed_company_ids.ids

    def is_allowed_for_any_company(self, company_ids):
        """
        Verifica si la ubicación es utilizable por *al menos una* de las
        empresas indicadas.

        :param company_ids: iterable de ids de empresa.
        :return: ``True`` si al menos una empresa puede usar la ubicación.
        """
        self.ensure_one()
        ids = list(company_ids)

        if self._is_technical_location():
            return True

        if not self.allowed_company_ids:
            if not self.company_id:
                return True
            return self.company_id.id in ids

        return bool(set(self.allowed_company_ids.ids) & set(ids))

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _is_technical_location(self):
        """
        Devuelve ``True`` si la ubicación es técnica/estándar de Odoo y
        debe estar exenta de las restricciones de este módulo.

        Criterios:
        - ``usage`` en ('customer', 'supplier', 'inventory', 'production')
        - ``scrap_location == True``  (campo Boolean disponible en Odoo 18)
        - Ubicación raíz de tipo 'view' sin padre (Physical/Virtual Locations)

        Nota: ``return_location`` fue eliminado en Odoo 18; no se usa.
        """
        self.ensure_one()
        if self.usage in _TECHNICAL_USAGES:
            return True
        # scrap_location existe en Odoo 18 como Boolean
        if hasattr(self, 'scrap_location') and self.scrap_location:
            return True
        # Raíces (sin padre) de tipo view
        if self.usage == 'view' and not self.location_id:
            return True
        return False

    # ------------------------------------------------------------------
    # Override create: default de allowed_company_ids para nuevas ubics.
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear una ubicación nueva, si ``allowed_company_ids`` no fue
        especificado explícitamente, se inicializa con:
        - La empresa de ``company_id`` si está definida.
        - La empresa activa del usuario en caso contrario.

        Las ubicaciones técnicas quedan exentas.
        """
        records = super().create(vals_list)

        for record, vals in zip(records, vals_list):
            # Respetar si ya viene en vals (incluyendo lista vacía explícita)
            if 'allowed_company_ids' in vals:
                continue
            if record._is_technical_location():
                continue

            if record.company_id:
                target_id = record.company_id.id
            elif self.env.company:
                target_id = self.env.company.id
            else:
                continue

            # sudo() para evitar problemas de acceso en flujos automatizados
            record.sudo().write({
                'allowed_company_ids': [(4, target_id)],
            })
            _logger.debug(
                'StockLocation.create: allowed_company_ids inicializado '
                'con empresa %s para ubicación "%s" (id=%s)',
                target_id, record.complete_name, record.id,
            )

        return records
