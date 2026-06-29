# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ProjectTask(models.Model):
    _inherit = 'project.task'

    installation_material_ids = fields.One2many(
        'sale.installation.material', 'task_id', string='Controles de Materiales')
    installation_material_count = fields.Integer(compute='_compute_installation_material_count')

    @api.depends('installation_material_ids')
    def _compute_installation_material_count(self):
        for task in self:
            task.installation_material_count = len(task.installation_material_ids)

    def action_view_installation_material(self):
        self.ensure_one()
        controls = self.installation_material_ids
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Control de Materiales'),
            'res_model': 'sale.installation.material',
            'context': {'create': False},
        }
        if len(controls) == 1:
            action.update({'view_mode': 'form', 'res_id': controls.id})
        else:
            action.update({
                'view_mode': 'list,form',
                'domain': [('task_id', '=', self.id)],
            })
        return action
