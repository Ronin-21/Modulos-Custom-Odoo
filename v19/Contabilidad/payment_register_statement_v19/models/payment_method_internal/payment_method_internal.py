# -*- coding: utf-8 -*-
import base64
import re

from odoo import Command, api, fields, models, _


_TRANSPARENT_PNG = base64.b64encode(
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82'
).decode()


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('prs_internal', 'Payment Register interno')],
        ondelete={'prs_internal': 'set default'},
    )
    prs_internal_provider = fields.Boolean(
        string='Proveedor interno Payment Register',
        help='Proveedor tecnico no publicado usado para activar metodos y marcas de pago para POS y pagos internos.',
    )

    @api.depends('code')
    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        for provider in self.filtered(lambda p: p.code == 'prs_internal'):
            provider.support_express_checkout = False
            provider.support_manual_capture = False
            provider.support_tokenization = False
            provider.support_refund = 'none'

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.code != 'prs_internal':
            return super()._get_default_payment_method_codes()
        methods = self.with_context(active_test=False).payment_method_ids
        return set(methods.mapped('code') + methods.mapped('brand_ids.code'))

    @api.model
    def _prs_get_internal_providers(self, companies=None):
        companies = companies or self.env['res.company'].sudo().search([])
        Provider = self.sudo().with_context(active_test=False)
        providers = Provider.search([('code', '=', 'prs_internal')])
        company_to_provider = {provider.company_id.id: provider for provider in providers}
        created = self.env['payment.provider']
        for company in companies:
            if company.id in company_to_provider:
                continue
            provider_vals = {
                'name': 'Payment Register Interno - %s' % company.display_name,
                'code': 'prs_internal',
                'state': 'enabled',
                'is_published': False,
                'company_id': company.id,
                'prs_internal_provider': True,
            }
            created |= Provider.create(provider_vals)
        providers |= created
        providers.filtered(lambda p: not p.prs_internal_provider).write({'prs_internal_provider': True})
        providers.filtered(lambda p: p.is_published).write({'is_published': False})
        providers.filtered(lambda p: p.state == 'disabled').write({'state': 'enabled', 'is_published': False})
        return providers

    @api.model
    def _prs_ensure_internal_provider(self):
        providers = self._prs_get_internal_providers()
        PaymentMethod = self.env['payment.method'].sudo().with_context(active_test=False)
        methods = PaymentMethod.search([])
        if methods and providers:
            for method in methods:
                missing = providers - method.provider_ids
                if missing:
                    method.with_context(prs_skip_internal_provider_link=True).write({
                        'provider_ids': [Command.link(provider.id) for provider in missing]
                    })
                if not method.active:
                    method.with_context(prs_skip_internal_provider_link=True).write({'active': True})
                if method.brand_ids:
                    inactive_brands = method.brand_ids.with_context(active_test=False).filtered(lambda b: not b.active)
                    for brand in inactive_brands:
                        missing_brand = providers - brand.provider_ids
                        if missing_brand:
                            brand.with_context(prs_skip_internal_provider_link=True).write({
                                'provider_ids': [Command.link(provider.id) for provider in missing_brand]
                            })
                        brand.with_context(prs_skip_internal_provider_link=True).write({'active': True})
        return providers

    def init(self):
        # Solo crea proveedores para empresas que aún no tienen uno,
        # evitando repetir el trabajo del post_init_hook en cada upgrade.
        try:
            companies = self.env['res.company'].sudo().search([])
            existing_ids = set(
                self.sudo().with_context(active_test=False)
                .search([('code', '=', 'prs_internal')])
                .mapped('company_id.id')
            )
            if set(companies.ids) - existing_ids:
                self.env['payment.provider']._prs_ensure_internal_provider()
        except Exception:
            pass


class PaymentMethod(models.Model):
    _inherit = 'payment.method'

    def _prs_make_internal_code(self, name):
        base = re.sub(r'[^a-z0-9]+', '_', (name or 'metodo').strip().lower()).strip('_') or 'metodo'
        base = 'prs_%s' % base
        code = base
        index = 1
        while 'code' in self._fields and self.with_context(active_test=False).search([('code', '=', code)], limit=1):
            index += 1
            code = '%s_%s' % (base, index)
        return code

    def _prs_prepare_payment_method_vals(self, vals):
        if 'code' in self._fields and not vals.get('code'):
            vals['code'] = self._prs_make_internal_code(vals.get('name'))
        if 'image' in self._fields and not vals.get('image'):
            vals['image'] = _TRANSPARENT_PNG
        providers = self.env['payment.provider']._prs_get_internal_providers()
        if providers:
            commands = list(vals.get('provider_ids') or [])
            for provider in providers:
                commands.append(Command.link(provider.id))
            vals['provider_ids'] = commands
        if 'active' not in vals:
            vals['active'] = True
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prs_prepare_payment_method_vals(dict(vals)) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if vals.get('active') and not vals.get('provider_ids'):
            providers = self.env['payment.provider']._prs_get_internal_providers()
            if providers:
                for method in self.with_context(active_test=False):
                    missing = providers - method.provider_ids
                    if missing:
                        method.with_context(prs_skip_internal_provider_link=True).write({
                            'provider_ids': [Command.link(provider.id) for provider in missing]
                        })
        result = super().write(vals)
        if not self.env.context.get('prs_skip_internal_provider_link') and any(key in vals for key in ('provider_ids', 'active', 'primary_payment_method_id')):
            providers = self.env['payment.provider']._prs_get_internal_providers()
            for method in self.with_context(active_test=False):
                missing = providers - method.provider_ids
                if missing:
                    method.with_context(prs_skip_internal_provider_link=True).write({'provider_ids': [Command.link(provider.id) for provider in missing]})
        return result
