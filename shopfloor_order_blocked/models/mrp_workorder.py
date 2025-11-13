from odoo import fields, models, api, _
from odoo.exceptions import UserError


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    is_blocked_by_dependency = fields.Boolean(
        string="Bloqueada por dependencias",
        compute="_compute_is_blocked_by_dependency",
        store=False,
    )
    
    blocking_workorder_names = fields.Char(
        string="Operaciones bloqueantes",
        compute="_compute_is_blocked_by_dependency",
        store=False,
    )

    @api.depends("blocked_by_workorder_ids", "blocked_by_workorder_ids.state", 
                 "production_bom_id.enforce_workorder_dependency", "state")
    def _compute_is_blocked_by_dependency(self):
        """
        Determina si la orden de trabajo está bloqueada por dependencias no completadas.
        """
        for rec in self:
            rec.is_blocked_by_dependency = False
            rec.blocking_workorder_names = ""
            
            # Solo aplicar si está habilitado en el BOM y no está en estado final
            if not rec.production_bom_id.enforce_workorder_dependency:
                continue
            
            if rec.state in ['done', 'cancel']:
                continue
            
            # Verificar si tiene dependencias bloqueantes
            if rec.blocked_by_workorder_ids:
                blocking_orders = rec.blocked_by_workorder_ids.filtered(
                    lambda wo: wo.state not in ['done', 'cancel']
                )
                if blocking_orders:
                    rec.is_blocked_by_dependency = True
                    rec.blocking_workorder_names = ", ".join(blocking_orders.mapped('name'))

    def button_start(self):
        """
        Sobrescribe el botón de inicio para validar dependencias.
        """
        # Validar dependencias (si implementaste esta lógica)
        for workorder in self:
            if workorder.is_blocked_by_dependency:
                raise UserError(_(
                    "No es posible iniciar la operación '%s' porque depende de las "
                    "siguientes operaciones que aún no han sido completadas:\n\n%s\n\n"
                    "Por favor, completa primero las operaciones anteriores."
                ) % (workorder.name, workorder.blocking_workorder_names))
            
            # Validar capacidad del centro de trabajo
            workcenter = workorder.workcenter_id
            if workcenter:
                # Contar cuántas workorders están en ejecución en este centro
                active_orders = self.env['mrp.workorder'].search_count([
                    ('workcenter_id', '=', workcenter.id),
                    ('state', '=', 'progress'),  # Operaciones en curso
                    ('id', '!=', workorder.id),  # Excluir la actual
                ])
                
                if active_orders >= workcenter.default_capacity:
                    raise UserError(_(
                        "El centro de trabajo '%s' ya está en uso.\n\n"
                        "Capacidad máxima: %d operación(es).\n"
                        "Órdenes en ejecución: %d.\n\n"
                        "Por favor espera a que finalice alguna operación antes de iniciar '%s'."
                    ) % (workcenter.name, workcenter.default_capacity, active_orders, workorder.name))
        
        return super().button_start()
    
    def button_finish(self):
        """
        Sobrescribe el botón de finalizar para asegurar que se actualicen los estados correctamente.
        """
        res = super().button_finish()
        # Forzar recálculo de dependencias en órdenes de trabajo relacionadas
        dependent_workorders = self.env['mrp.workorder'].search([
            ('blocked_by_workorder_ids', 'in', self.ids)
        ])
        if dependent_workorders:
            dependent_workorders._compute_is_blocked_by_dependency()
        return res
