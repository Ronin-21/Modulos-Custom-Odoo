from odoo import fields, models, api, _

class remove_action(models.Model):

    def _invalidate_access_management_caches(self):
        self.env.registry.clear_cache()
        self.env.registry.clear_cache('templates')

    _name = 'remove.action'
    _description = "Permisos del modelo"


    access_management_id = fields.Many2one('access.management', 'Gestión de accesos')
    model_id = fields.Many2one('ir.model', 'Model')
    view_data_ids = fields.Many2many('view.data', 'remove_action_view_data_rel_ah', 'remove_action_id', 
                                     'view_data_id', 'Ocultar vistas',
                                     help="The views are added on list will be hidden in selected model from the defined users.")
    server_action_ids = fields.Many2many('action.data' ,'remove_action_server_action_data_rel_ah', 
                                         'remove_action_id', 'server_action_id', 'Ocultar acciones', 
                                         domain="[('action_id.binding_model_id','=',model_id),('action_id.type','!=','ir.actions.report')]",
                                         help="The actions are added on list will be hidden in selected model from the defined users.")
    report_action_ids = fields.Many2many('action.data' ,'remove_action_report_action_data_rel_ah', 
                                         'remove_action_id', 'report_action_id', 'Ocultar reportes', 
                                         domain="[('action_id.binding_model_id','=',model_id),('action_id.type','=','ir.actions.report')]",
                                         help="The Reports are added on list will be hidden in selected model from the defined users.")
    restrict_export = fields.Boolean('Ocultar exportación' , help="Export Button will be hidden in selected model from the defined users.")
    restrict_import = fields.Boolean('Ocultar importación', help="Import Button will be hidden in selected model from the defined users.")
    readonly = fields.Boolean('Solo lectura')

    restrict_create = fields.Boolean('Ocultar crear', help="Create Button will be hidden in selected model from the defined users.")
    restrict_edit = fields.Boolean('Ocultar editar', help="Edit Button will be hidden in selected model from the defined users.")
    restrict_delete = fields.Boolean('Ocultar eliminar', help="Delete Button will be hidden in selected model from the defined users.")
    restrict_archive_unarchive = fields.Boolean('Ocultar archivar/desarchivar', help="Archive and Unarchive action will be hidden in selected model from the defined users.")
    restrict_duplicate = fields.Boolean('Ocultar duplicar', help="Duplicate action will be hidden in selected model from the defined users.")
    restrict_chatter = fields.Boolean('Ocultar chatter', help="The Chatter will be hidden in selected model from the defined users.")
    restrict_spreadsheet = fields.Boolean('Ocultar hoja de cálculo')

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self._invalidate_access_management_caches()
        return res

    def write(self, vals):
        res = super().write(vals)
        self._invalidate_access_management_caches()
        return res

    def unlink(self):
        res = super().unlink()
        self._invalidate_access_management_caches()
        return res
