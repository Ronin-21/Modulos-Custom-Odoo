# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import UserError


class ReportInternalTransferRemit(models.AbstractModel):
    _name = "report.stock_internal_transfer_remit.itr_remit"
    _description = "Remito de Traslado Interno"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["stock.picking"].browse(docids).exists()
        non_internal = docs.filtered(lambda picking: picking.picking_type_id.code != "internal")
        if non_internal:
            raise UserError(_("El Remito de Traslado Interno solo puede imprimirse en traslados internos."))
        return {
            "doc_ids": docs.ids,
            "doc_model": "stock.picking",
            "docs": docs,
        }
