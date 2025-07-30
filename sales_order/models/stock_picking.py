from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super(StockPicking, self).button_validate()

        for picking in self:
            if picking.picking_type_id.code != 'outgoing':
                continue

            if not picking.origin:
                continue

            # Find the related sale order
            sales_order = self.env['sale.order'].search([('name', '=', picking.origin)], limit=1)
            if not sales_order:
                continue

            # Update the warehouse status without creating duplicate lines
            sales_order.write({'warehouse_status': 'assigned_to_shipping'})

            for move in picking.move_ids_without_package:
                existing_line = sales_order.order_line.filtered(
                    lambda l: l.product_id == move.product_id
                )
                print('existing_line',existing_line)

                if existing_line:
                    zero_qty_lines = existing_line.filtered(lambda l: l.product_uom_qty == 0)
                    if zero_qty_lines:
                        zero_qty_lines.unlink()

            sales_order.write({'state': 'sale'})



        return res