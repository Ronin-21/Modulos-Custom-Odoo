# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

DEFAULT_SURCHARGE_PRODUCT_NAME = "Recargo POS"
DEFAULT_SURCHARGE_PRODUCT_CODE_PREFIX = "POS_SURCHARGE_"


def _get_or_create_surcharge_product(env, company):
    """Return a product.product to be used as POS surcharge product for `company`.

    We create ONE product per company (company_id set), with available_in_pos enabled.
    The product is identified by an internal reference (default_code) using the company id.
    """
    code = f"{DEFAULT_SURCHARGE_PRODUCT_CODE_PREFIX}{company.id}"

    Product = env["product.product"].sudo().with_company(company)
    # company_id is a related field on product.product (through product.template)
    prod = Product.search([("default_code", "=", code), ("company_id", "=", company.id)], limit=1)
    if prod:
        return prod

    # Create a product.template and use its single variant
    tmpl_vals = {
        "name": DEFAULT_SURCHARGE_PRODUCT_NAME,
        "company_id": company.id,
        "available_in_pos": True,
        "sale_ok": True,
        "purchase_ok": False,
        "list_price": 0.0,
    }
    Template = env["product.template"].sudo().with_company(company)
    # Compatibility across versions: detailed_type is the canonical field; type may exist as alias/related
    if "detailed_type" in Template._fields:
        tmpl_vals["detailed_type"] = "service"
    elif "type" in Template._fields:
        tmpl_vals["type"] = "service"

    tmpl = Template.create(tmpl_vals)
    prod = tmpl.product_variant_id.sudo().with_company(company)

    if "default_code" in prod._fields:
        prod.default_code = code

    return prod


def _assign_surcharge_product_to_missing_methods(env, company, product):
    """Assign surcharge product to payment methods of POS configs for the given company
    that use surcharge adjustment and don't have an adjustment_product_id yet.
    """
    Config = env["pos.config"].sudo().with_company(company)
    configs = Config.search([("company_id", "=", company.id)])
    if not configs:
        return

    payment_methods = configs.mapped("payment_method_ids")
    missing = payment_methods.filtered(
        lambda m: m.apply_adjustment and m.adjustment_type == "surcharge" and not m.adjustment_product_id
    )
    if missing:
        missing.write({"adjustment_product_id": product.id})


def ensure_surcharge_products(env):
    """Ensure the surcharge product exists ONLY for companies that actually use it.

    We limit creation to companies that have at least one POS configuration where a payment method
    has apply_adjustment enabled with adjustment_type = 'surcharge'. This avoids cluttering the
    database in environments with many companies.
    """
    Config = env["pos.config"].sudo()
    configs = Config.search([])
    if not configs:
        return

    companies = configs.mapped("company_id")
    for company in companies:
        company_configs = configs.filtered(lambda c: c.company_id.id == company.id)
        payment_methods = company_configs.mapped("payment_method_ids").filtered(
            lambda m: m.apply_adjustment and m.adjustment_type == "surcharge"
        )
        if not payment_methods:
            continue

        prod = _get_or_create_surcharge_product(env, company)
        _assign_surcharge_product_to_missing_methods(env, company, prod)


def post_init_hook(*args, **kwargs):
    """Create/ensure one surcharge product per company and assign it to missing payment methods.

    Odoo versions differ in how they call hooks:
    - Some call post_init_hook(cr, registry)
    - Others call post_init_hook(env)

    We support both calling conventions.
    """
    env = None

    # Newer convention: called with a single Environment
    if len(args) == 1 and hasattr(args[0], "cr") and hasattr(args[0], "__getitem__"):
        env = args[0]

    # Older convention: called with (cr, registry)
    if env is None and len(args) >= 1:
        cr = args[0]
        try:
            env = api.Environment(cr, SUPERUSER_ID, {})
        except Exception:
            env = None

    if env is None:
        return

    ensure_surcharge_products(env)