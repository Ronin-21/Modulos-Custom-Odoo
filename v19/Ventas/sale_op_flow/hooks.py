# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

DISCOUNT_CODE_PREFIX = 'SOF_DISCOUNT_'
SURCHARGE_CODE_PREFIX = 'SOF_SURCHARGE_'


def _get_or_create_adjustment_product(env, company, product_type):
    if product_type == 'discount':
        code = f'{DISCOUNT_CODE_PREFIX}{company.id}'
        name = 'Descuento medio de pago'
    else:
        code = f'{SURCHARGE_CODE_PREFIX}{company.id}'
        name = 'Recargo medio de pago'

    Product = env['product.product'].sudo().with_company(company)
    existing = Product.search(
        [('default_code', '=', code), ('company_id', '=', company.id)], limit=1
    )
    if existing:
        return existing

    Template = env['product.template'].sudo().with_company(company)
    tmpl_vals = {
        'name': name,
        'company_id': company.id,
        'sale_ok': False,
        'purchase_ok': False,
        'list_price': 0.0,
        'taxes_id': [(5, 0, 0)],
    }
    if 'detailed_type' in Template._fields:
        tmpl_vals['detailed_type'] = 'service'
    else:
        tmpl_vals['type'] = 'service'

    tmpl = Template.create(tmpl_vals)
    prod = tmpl.product_variant_id.sudo().with_company(company)
    prod.default_code = code
    return prod


def post_init_hook(*args, **kwargs):
    env = None
    if len(args) == 1 and hasattr(args[0], 'cr'):
        env = args[0]
    if env is None and len(args) >= 1:
        try:
            env = api.Environment(args[0], SUPERUSER_ID, {})
        except Exception:
            env = None
    if env is None:
        return
    companies = env['res.company'].sudo().search([])
    for company in companies:
        _get_or_create_adjustment_product(env, company, 'discount')
        _get_or_create_adjustment_product(env, company, 'surcharge')
