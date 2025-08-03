from xml import etree

from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sale_order_return_count=fields.Integer(compute='return_count')

    def return_count(self):
        for rec in self:
            rec.sale_order_return_count=len(self.env['sale.order.return'].search([('sale_order_id','=',self.id)]))

    def action_open_return_wizard(self):

        returnable_lines = self.order_line.filtered(lambda line: line.product_uom_qty >= line.return_qty)

        if not returnable_lines:
            raise UserError('You Cannot Make Return Because No Items Available for Return')

        return_order = self.env['sale.order.return'].create({
            'customer_id': self.partner_id.id,
            'sale_order_id': self.id,
        })

        # Create return lines for each order line
        for line in returnable_lines:
            self.env['sale.order.return.lines'].create({
                'return_id': return_order.id,
                'product_id': line.product_id.id,
                'qty': line.product_uom_qty,
                'price_unit': line.price_unit
            })

        # Return the view of the newly created return order
        return {
            'name': 'Return Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.return',
            'view_mode': 'form',
            'res_id': return_order.id,
            'target': 'current',
        }

    def View_return_order(self):

            print(self.id)

            return {
              'name': 'Sale Return',
             'type': 'ir.actions.act_window',
             'res_model': 'sale.order.return',
              'view_mode': 'list,form',
                'target': 'current',
                'domain': [('sale_order_id', '=', self.id)],
            }







class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    return_qty=fields.Integer('Return')