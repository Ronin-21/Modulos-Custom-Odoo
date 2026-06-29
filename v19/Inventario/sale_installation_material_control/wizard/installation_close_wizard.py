# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class InstallationCloseWizard(models.TransientModel):
    _name = 'installation.close.wizard'
    _description = 'Asistente de Cierre de Instalación'

    installation_id = fields.Many2one(
        'sale.installation.material', string='Control', required=True, readonly=True)
    adjust_so_qty = fields.Boolean(string='Ajustar cantidad de la venta al consumo real')
    allow_close_with_installer_material = fields.Boolean(readonly=True)
    in_installer_total = fields.Float(
        string='En poder del instalador', readonly=True, digits='Product Unit of Measure')
    confirm_installer_material = fields.Boolean(
        string='Confirmo que el material en poder del instalador fue consumido')
    line_ids = fields.One2many(
        'installation.close.wizard.line', 'wizard_id', string='Resumen', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        installation = self.env['sale.installation.material'].browse(
            res.get('installation_id') or self.env.context.get('default_installation_id'))
        if installation:
            company = installation.company_id
            res.setdefault('installation_id', installation.id)
            res['adjust_so_qty'] = company.installation_adjust_so_qty_on_close
            res['allow_close_with_installer_material'] = \
                company.installation_allow_close_with_installer_material
            res['in_installer_total'] = sum(installation.line_ids.mapped('in_installer_qty'))
            res['line_ids'] = [
                (0, 0, {
                    'product_id': line.product_id.id,
                    'original_qty': line.original_qty,
                    'used_qty': line.used_qty,
                    'released_qty': line.original_qty - line.used_qty,
                })
                for line in installation.line_ids
            ]
        return res

    def action_confirm(self):
        self.ensure_one()
        installation = self.installation_id
        if (float_compare(self.in_installer_total, 0.0, precision_digits=2) > 0
                and not self.allow_close_with_installer_material
                and not self.confirm_installer_material):
            raise UserError(_(
                'Hay material en poder del instalador (%.2f). Marcá la confirmación de consumo '
                'para cerrar, o registrá la devolución correspondiente.') % self.in_installer_total)
        installation._do_close(adjust_so_qty=self.adjust_so_qty)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.installation.material',
            'res_id': installation.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }


class InstallationCloseWizardLine(models.TransientModel):
    _name = 'installation.close.wizard.line'
    _description = 'Línea de resumen de cierre de instalación'

    wizard_id = fields.Many2one(
        'installation.close.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', readonly=True)
    original_qty = fields.Float(
        string='Presupuestado', readonly=True, digits='Product Unit of Measure')
    used_qty = fields.Float(
        string='Usado real (a facturar)', readonly=True, digits='Product Unit of Measure')
    released_qty = fields.Float(
        string='Liberado a stock', readonly=True, digits='Product Unit of Measure')
