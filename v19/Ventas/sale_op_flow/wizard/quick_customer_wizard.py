# -*- coding: utf-8 -*-
"""
sale.quick.customer.wizard — Creación rápida de cliente

Formulario simplificado para que el vendedor cree un cliente
sin salir del módulo. Solo pide los datos esenciales.
La empresa se precarga desde el contexto de la compañía activa.
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleQuickCustomerWizard(models.TransientModel):
    _name = 'sale.quick.customer.wizard'
    _description = 'Crear Cliente Rápido'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Pedido',
        required=True,
        readonly=True,
    )

    # ── Tipo de cliente ───────────────────────────────────────────────────────
    company_type = fields.Selection(
        [('person', 'Persona física'), ('company', 'Empresa / Razón social')],
        string='Tipo',
        default='person',
        required=True,
    )

    # ── Datos básicos ─────────────────────────────────────────────────────────
    name = fields.Char(
        string='Nombre / Razón Social',
        required=True,
    )

    vat = fields.Char(
        string='CUIT / DNI',
        help='Número de identificación fiscal del cliente.',
    )

    # ── Contacto ──────────────────────────────────────────────────────────────
    phone = fields.Char(string='Teléfono')
    mobile = fields.Char(string='Celular')
    email = fields.Char(string='Email')

    # ── Empresa relacionada (si es persona) ───────────────────────────────────
    parent_id = fields.Many2one(
        'res.partner',
        string='Empresa a la que pertenece',
        domain=[('is_company', '=', True)],
        help='Solo para personas físicas: empresa a la que pertenecen.',
    )

    # ── Dirección (opcional) ──────────────────────────────────────────────────
    street = fields.Char(string='Dirección')
    city = fields.Char(string='Ciudad / Localidad')

    # ── Empresa Odoo (precargada, para multi-company) ─────────────────────────
    company_id = fields.Many2one(
        'res.company',
        string='Empresa (sistema)',
        default=lambda self: self.env.company,
        readonly=True,
    )

    # ── Validaciones ──────────────────────────────────────────────────────────
    @api.constrains('name')
    def _check_name(self):
        for wiz in self:
            if not wiz.name or not wiz.name.strip():
                raise ValidationError(_('El nombre del cliente es obligatorio.'))

    @api.onchange('company_type')
    def _onchange_company_type(self):
        """Si cambia a Empresa, limpiar el campo parent_id."""
        if self.company_type == 'company':
            self.parent_id = False

    # ── Acción: crear y asignar al pedido ─────────────────────────────────────
    def action_create_customer(self):
        """
        Crea el res.partner con los datos ingresados,
        lo marca como cliente (customer_rank=1) y lo asigna al pedido.
        """
        self.ensure_one()

        vals = {
            'name': self.name.strip(),
            'is_company': self.company_type == 'company',
            'customer_rank': 1,  # Es cliente
            'supplier_rank': 0,
        }

        if self.vat:
            vals['vat'] = self.vat.strip()
        if self.phone:
            vals['phone'] = self.phone
        if self.mobile:
            vals['mobile'] = self.mobile
        if self.email:
            vals['email'] = self.email.strip()
        if self.street:
            vals['street'] = self.street
        if self.city:
            vals['city'] = self.city
        if self.parent_id and self.company_type == 'person':
            vals['parent_id'] = self.parent_id.id

        partner = self.env['res.partner'].create(vals)

        # Asignar al pedido de venta
        self.sale_order_id.partner_id = partner

        # Mostrar notificación de éxito y cerrar wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cliente creado'),
                'message': _('"%s" fue creado y asignado al presupuesto.') % partner.name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
