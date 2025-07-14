from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    phone = fields.Char(related='partner_id.phone', string="Phone", store=True)
    phone2 = fields.Char(related='partner_id.phone2', string="Phone 2", store=True)
    gender = fields.Selection(related='partner_id.gender', string="Gender", store=True)
