from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        print('validfd')
        for rec in self:
            sales_order=self.env['sale.order'].search([('name','=',rec.origin)],limit=1)
            if sales_order:
                print('sales_order',sales_order)
                sales_order.warehouse_status='assigned_to_shipping'

        return super(StockPicking,self).button_validate()
