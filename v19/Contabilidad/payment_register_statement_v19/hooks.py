# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def _hook_env(*args):
    if len(args) == 1 and hasattr(args[0], 'cr') and hasattr(args[0], '__getitem__'):
        return args[0]
    if args:
        try:
            return api.Environment(args[0], SUPERUSER_ID, {})
        except Exception:
            return None
    return None


def _ensure_internal_payment_method_catalog(env):
    if 'payment.method' not in env:
        return
    Method = env['payment.method'].sudo().with_context(active_test=False)

    def make_code(name):
        import re
        base = re.sub(r'[^a-z0-9]+', '_', (name or 'metodo').strip().lower()).strip('_') or 'metodo'
        code = 'prs_%s' % base
        idx = 1
        while 'code' in Method._fields and Method.search([('code', '=', code)], limit=1):
            idx += 1
            code = 'prs_%s_%s' % (base, idx)
        return code

    for name in ('Tarjeta', 'QR', 'PIX'):
        rec = Method.search([('name', '=', name), ('primary_payment_method_id', '=', False)], limit=1)
        if rec:
            if 'active' in Method._fields and not rec.active:
                rec.write({'active': True})
            continue
        vals = {'name': name}
        if 'code' in Method._fields:
            vals['code'] = make_code(name)
        if 'is_primary' in Method._fields:
            vals['is_primary'] = True
        if 'primary_payment_method_id' in Method._fields:
            vals['primary_payment_method_id'] = False
        if 'active' in Method._fields:
            vals['active'] = True
        try:
            Method.create(vals)
        except Exception:
            # Keep install defensive; users can still create the catalog manually.
            pass


def post_init_hook(*args, **kwargs):
    env = _hook_env(*args)
    if not env:
        return
    try:
        _ensure_internal_payment_method_catalog(env)
        env['payment.provider']._prs_ensure_internal_provider()
    except Exception:
        pass
