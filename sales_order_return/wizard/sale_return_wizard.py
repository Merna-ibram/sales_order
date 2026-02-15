from odoo import models, fields, api
from odoo.exceptions import UserError

class ReturnWizard(models.TransientModel):
    _name = 'return.wizard'
    _description = 'Return Order Wizard'

    user_id = fields.Many2one('res.users', string='المستخدم', default=lambda self: self.env.user)
    customer_id=fields.Many2one('res.partner',string='Customer')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    return_reason = fields.Text(string='Return Reason')
    return_line_ids = fields.One2many('return.wizard.line', 'wizard_id', string='Return Lines')
    date_return = fields.Date(string="تاريخ الإرجاع", default=fields.Date.context_today)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        print('Context:', self.env.context)

        if self.env.context.get('active_model') == 'sale.order' and self.env.context.get('active_id'):
            sale_order = self.env['sale.order'].browse(self.env.context['active_id'])
            print('Sale order:', sale_order.name)
            print('Order lines count:', len(sale_order.order_line))

            res['sale_order_id'] = sale_order.id
            res['customer_id'] = sale_order.partner_id.id
            return_lines = []

            for line in sale_order.order_line:
                print(f'Processing line: {line.product_id.name}, qty: {line.product_uom_qty}')
                line_data = {
                    'product_id': line.product_id.id,
                    'original_qty': line.product_uom_qty,
                    'return_qty': line.product_uom_qty,
                    'sale_line_id': line.id,
                    'product_uom': line.product_uom.id,
                }
                return_lines.append((0, 0, line_data))
                print('Line data created:', line_data)

            res['return_line_ids'] = return_lines
            print('Total return lines created:', len(return_lines))
        else:
            print('No active sale order found in context')

        return res

    def action_submit_return(self):
        # Create a new return record in sale.order.return model
        return_order = self.env['sale.order.return'].create({
            'user_id': self.user_id.id,
            'customer_id': self.customer_id.id,
            'sale_order_id': self.sale_order_id.id,
            'return_reason': self.return_reason,
            'date_return': self.date_return,
        })

        # Create return lines
        for line in self.return_line_ids:
            print(line.product_id_int)
            self.env['sale.order.return.lines'].create({
                'return_id': return_order.id,
                'product_id': line.product_id_int,  # Fixed: using line.product_id.id
                'qty': line.return_qty,
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

    # def action_submit_return(self):
    #     self.ensure_one()
    #     sale_order = self.sale_order_id
    #
    #     # Debug: Print sale order and return lines
    #     print("=== DEBUG: Sale Order ===")
    #     print(sale_order)
    #     print("=== DEBUG: Return Lines ===")
    #     for line in self.return_line_ids:
    #         print(
    #             f"Product: {line.product_id.name if line.product_id else 'None'}, "
    #             f"Qty: {line.return_qty}, "
    #             f"UoM: {line.product_uom.name if line.product_uom else 'None'}"
    #         )
    #
    #     # Check if there's a completed delivery
    #     original_picking = self.env['stock.picking'].search([
    #         ('origin', '=', sale_order.name),
    #         ('state', '=', 'done')
    #     ], limit=1)
    #     print('original_picking', original_picking)
    #
    #     if not original_picking:
    #         raise UserError("لا يمكن إرجاع المنتجات لأن أمر التسليم لم يُنفذ بعد.")
    #
    #     # Find the return picking type (incoming)
    #     picking_type = self.env['stock.picking.type'].search([
    #         ('code', '=', 'incoming'),
    #         ('warehouse_id', '=', sale_order.warehouse_id.id)
    #     ], limit=1)
    #     print('picking_type', picking_type)
    #
    #     if not picking_type:
    #         raise UserError("لم يتم العثور على نوع عملية الإرجاع (incoming) للمستودع.")
    #
    #     # Create the return picking
    #     return_picking = self.env['stock.picking'].create({
    #         'origin': f"Return - {original_picking.name}",
    #         'partner_id': sale_order.partner_id.id,
    #         'picking_type_id': picking_type.id,
    #         'location_id': sale_order.partner_id.property_stock_customer.id,
    #         'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
    #         'move_type': 'direct',
    #         'sale_id':sale_order.id
    #
    #     })
    #     print('return_picking', return_picking)
    #
    #     # Create stock moves by matching return lines with sale order lines
    #     move_ids = []
    #     for line in self.return_line_ids:
    #         if line.return_qty <= 0:
    #             continue  # Skip if return quantity is zero or negative
    #
    #         # Find the corresponding sale order line
    #         for line_order in sale_order.order_line:
    #
    #            move = self.env['stock.move'].create({
    #             'name': f"Return: {line.product_id.name}",
    #             'product_id': line_order.product_id.id,  # Now using line_order
    #             'product_uom_qty': line.return_qty,
    #             'quantity': line.return_qty,
    #             'product_uom': line_order.product_uom.id,  # Now using line_order
    #             'picking_id': return_picking.id,
    #             'location_id': sale_order.partner_id.property_stock_customer.id,
    #             'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
    #
    #            })
    #            move_ids.append(move.id)
    #            print('move', move)
    #
    #     if not move_ids:
    #         return_picking.unlink()
    #         raise UserError("لم يتم إنشاء أي منتجات للإرجاع، برجاء التأكد من الكميات.")
    #
    #     # Confirm and assign the picking
    #     return_picking.button_validate()
    #
    #     # Increment the return counter
    #     sale_order.num_returned += 1
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'تم بنجاح',
    #             'message': f'تم إنشاء أمر الإرجاع: {return_picking.name}',
    #             'type': 'success',
    #             'sticky': False,
    #             'next': {
    #                 'type': 'ir.actions.act_window_close'  # Close the wizard after showing the notification
    #             }
    #         }
    #     }
class ReturnWizardLine(models.TransientModel):
    _name = 'return.wizard.line'
    _description = 'Return Wizard Line'

    wizard_id = fields.Many2one('return.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product', )
    product_id_int=fields.Integer(compute='get_product_id',store=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Sale Line', readonly=True)
    original_qty = fields.Float(string='Original Quantity', readonly=True)
    return_qty = fields.Float(string='Return Quantity', default=0.0)
    # onhand_qty = fields.Float(string="الكمية المتاحة")
    delivered_qty = fields.Float(string='الكمية المسلمة', compute='_compute_delivery_return_qty')
    returned_qty = fields.Float(string='الكمية المرجعة مسبقًا', compute='_compute_delivery_return_qty')
    available_return_qty = fields.Float(string='الكمية المتاحة للإرجاع', compute='_compute_delivery_return_qty')
    product_uom=fields.Many2one('uom.uom','Units')


    def get_product_id(self):
        for rec in self:
            rec.product_id_int=rec.product_id.id

    @api.constrains('return_qty')
    def _check_return_qty(self):
        for line in self:
            if not line.product_id:
                continue
            if line.return_qty < 0:
                raise UserError('كمية الإرجاع لا يمكن أن تكون سالبة.')
            if line.return_qty > line.available_return_qty:
                raise UserError(
                    f"لا يمكن إرجاع أكثر من الكمية المتاحة للمنتج {line.product_id.display_name}.\n"
                    f"المتاحة للإرجاع: {line.available_return_qty}"
                )

    # def _compute_onhand_qty(self):
    #     for line in self:
    #         line.onhand_qty = line.product_id.qty_available if line.product_id else 0.0

    def _compute_delivery_return_qty(self):
        for line in self:
            delivered = sum(self.env['stock.move'].search([
                ('sale_line_id', '=', line.sale_line_id.id),
                ('state', '=', 'done')
            ]).mapped('quantity_done'))

            returned = sum(self.env['stock.move'].search([
                ('origin_returned_move_id.sale_line_id', '=', line.sale_line_id.id),
                ('state', '=', 'done')
            ]).mapped('product_uom_qty'))

            line.delivered_qty = delivered
            line.returned_qty = returned
            line.available_return_qty = max(delivered - returned, 0.0)



