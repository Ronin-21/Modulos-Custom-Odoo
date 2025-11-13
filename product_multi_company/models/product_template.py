# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    company_ids = fields.Many2many(
        'res.company',
        'product_template_company_rel',
        'product_id',
        'company_id',
        string='Empresas Permitidas',
        help='Empresas que pueden ver y usar este producto. '
             'Si está vacío, el producto será visible para todas las empresas.'
    )
    
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Override search para filtrar productos por empresas permitidas"""
        # Primero obtenemos todos los resultados sin filtrar
        res = super()._search(domain, offset=offset, limit=limit, order=order)
        
        # Si el usuario es superadmin, mostrar todos
        if self.env.su:
            return res
        
        # Obtener empresa actual del usuario
        current_company = self.env.company
        
        # Filtrar productos
        products = self.browse(res).filtered(
            lambda p: not p.company_ids or current_company in p.company_ids
        )
        
        return products.ids
    
    def write(self, vals):
        """Permitir escribir en productos de otras empresas si el campo company_ids lo permite"""
        # Remover temporalmente la validación de empresa
        return super(ProductTemplate, self.with_context(allowed_company_ids=self.env.companies.ids)).write(vals)
    
    @api.model
    def create(self, vals):
        """Permitir crear productos"""
        return super(ProductTemplate, self.with_context(allowed_company_ids=self.env.companies.ids)).create(vals)


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Override search para filtrar variantes por empresas permitidas"""
        res = super()._search(domain, offset=offset, limit=limit, order=order)
        
        # Si el usuario es superadmin, mostrar todos
        if self.env.su:
            return res
        
        current_company = self.env.company
        
        # Filtrar por el campo company_ids del template
        products = self.browse(res).filtered(
            lambda p: not p.product_tmpl_id.company_ids or 
                     current_company in p.product_tmpl_id.company_ids
        )
        
        return products.ids