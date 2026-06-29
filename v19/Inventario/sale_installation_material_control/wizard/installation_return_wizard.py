# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class InstallationReturnWizard(models.TransientModel):
    _name = 'installation.return.wizard'
    _description = 'Asistente de Devolución de Materiales de Instalación'

    installation_id = fields.Many2one(
        'sale.installation.material', string='Control', required=True, readonly=True)
    partner_id = fields.Many2one(related='installation_id.partner_id', readonly=True)
    responsible_user_id = fields.Many2one(
        'res.users', string='Responsable / Instalador', required=True)
    notes = fields.Text(string='Observaciones')
    line_ids = fields.One2many(
        'installation.return.wizard.line', 'wizard_id', string='Materiales')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        installation = self.env['sale.installation.material'].browse(
            res.get('installation_id') or self.env.context.get('default_installation_id'))
        if installation:
            res.setdefault('installation_id', installation.id)
            res.setdefault('responsible_user_id', installation.responsible_user_id.id)
            res['line_ids'] = [
                (0, 0, {
                    'installation_line_id': line.id,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom_id.id,
                    'in_installer_qty': line.in_installer_qty,
                    'qty': 0.0,
                })
                for line in installation.line_ids
                if float_compare(line.in_installer_qty, 0.0,
                                 precision_rounding=line.product_uom_id.rounding or 0.01) > 0
            ]
        return res

    def action_confirm(self):
        self.ensure_one()
        installation = self.installation_id
        installation._check_operational()

        to_process = self.line_ids.filtered(
            lambda l: float_compare(l.qty, 0.0,
                                    precision_rounding=l.product_uom_id.rounding or 0.01) > 0)
        if not to_process:
            raise UserError(_('Ingresá al menos una cantidad mayor a cero para devolver.'))

        pickings = self.env['stock.picking']
        for line in to_process:
            c_line = line.installation_line_id
            rounding = c_line.product_uom_id.rounding or 0.01
            if float_compare(line.qty, c_line.in_installer_qty, precision_rounding=rounding) > 0:
                raise UserError(_(
                    'No se puede devolver %(qty)s de %(prod)s: en poder del instalador hay %(av)s.',
                    qty=line.qty, prod=c_line.product_id.display_name,
                    av=c_line.in_installer_qty))
            picking = installation._run_internal_move(
                c_line, line.qty, 'return', responsible=self.responsible_user_id)
            pickings |= picking

        if self.notes:
            installation.message_post(body=_('Devolución por %(user)s: %(notes)s',
                                             user=self.responsible_user_id.name, notes=self.notes))
        detail = ', '.join('%s: %.2f' % (l.product_id.display_name, l.qty) for l in to_process)
        installation.message_post(body=_('📥 Devolución registrada por %(user)s. %(detail)s',
                                         user=self.responsible_user_id.name, detail=detail))

        if pickings:
            return self.env.ref(
                'sale_installation_material_control.action_report_installation_return'
            ).report_action(pickings)
        return {'type': 'ir.actions.act_window_close'}


class InstallationReturnWizardLine(models.TransientModel):
    _name = 'installation.return.wizard.line'
    _description = 'Línea de devolución de instalación'

    wizard_id = fields.Many2one(
        'installation.return.wizard', required=True, ondelete='cascade')
    installation_line_id = fields.Many2one(
        'sale.installation.material.line', string='Material', required=True, readonly=True)
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    product_uom_id = fields.Many2one('uom.uom', string='Unidad', readonly=True)
    in_installer_qty = fields.Float(
        string='En poder del instalador', readonly=True, digits='Product Unit of Measure')
    qty = fields.Float(string='A devolver', digits='Product Unit of Measure')
