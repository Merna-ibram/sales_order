
from odoo import models, fields, api
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _name = 'sale.order.return'


    _rec_name = 'name'

    name = fields.Char(
        string='Return Reference',
        required=True,
        readonly=True,
        copy=False,
        default='New'
    )
    user_id = fields.Many2one('res.users', string='المستخدم', default=lambda self: self.env.user,readonly=True)
    customer_id=fields.Many2one('res.partner',string='Customer',readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    return_reason = fields.Text(string='Return Reason' )
    return_line_ids = fields.One2many('sale.order.return.lines', 'return_id', string='Return Lines')
    date_return = fields.Date(string="تاريخ الإرجاع", default=fields.Date.context_today)
    state=fields.Selection([('cancel','Cancel'),('confirm','Confirm')],default='cancel')
    invoice_id = fields.Many2one('account.move')

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('sale.order.return') or 'New'
        return super(SaleOrder, self).create(vals)


    def action_confirm_return(self):
        sale_order=self.sale_order_id
        original_picking = self.env['stock.picking'].search([
                ('origin', '=', sale_order.name),
                ('state', '=', 'done')
            ], limit=1)
        print('original_picking', original_picking)

        if not original_picking:
                raise UserError("لا يمكن إرجاع المنتجات لأن أمر التسليم لم يُنفذ بعد.")

            # Find the return picking type (incoming)
        picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('warehouse_id', '=', sale_order.warehouse_id.id)
            ], limit=1)
        print('picking_type', picking_type)

        if not picking_type:
                raise UserError("لم يتم العثور على نوع عملية الإرجاع (incoming) للمستودع.")

            # Create the return picking
        return_picking = self.env['stock.picking'].create({
                'origin': f"Return - {original_picking.name}",
                'partner_id': sale_order.partner_id.id,
                'picking_type_id': picking_type.id,
                'location_id': sale_order.partner_id.property_stock_customer.id,
                'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
                'move_type': 'direct',
                'sale_id':sale_order.id,
                'return_ref':self.name

            })
        print('return_picking', return_picking)

        uom=self.env['uom.uom'].search([('name','=','Units')],limit=1)

            # Create stock moves by matching return lines with sale order lines
        move_ids = []
        for line in self.return_line_ids:
                if line.qty <= 0:
                    continue  # Skip if return quantity is zero or negative

                # Find the corresponding sale order line

                move = self.env['stock.move'].create({
                    'name': f"Return: {line.product_id.name}",
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.qty,
                    'quantity': line.qty,
                    'product_uom': uom.id,
                    'picking_id': return_picking.id,
                    'location_id': sale_order.partner_id.property_stock_customer.id,
                    'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,

                   })
        move_ids.append(move.id)
        print('move', move)

        if not move_ids:
                return_picking.unlink()
                raise UserError("لم يتم إنشاء أي منتجات للإرجاع، برجاء التأكد من الكميات.")

            # Confirm and assign the picking

            # Increment the return counter
        sale_order.num_returned += 1

        return {
            'name': 'Return Order',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': return_picking.id,
            'target': 'current',
        }
    def action_cancel_return(self):
        pass

    def action_credit_notes(self):
        for return_order in self:
            # Create credit note
            if self.invoice_id:
                print('exit')
                raise UserError(f'Invoice Create with name {self.invoice_id.name}')
                continue;
            else:
                print('create')
                invoice_vals = {
                'move_type': 'out_refund',
                'partner_id': return_order.sale_order_id.partner_id.id,
                'invoice_origin': return_order.sale_order_id.name,
                'invoice_line_ids': [],
                }

                for line in return_order.return_line_ids:
                    invoice_vals['invoice_line_ids'].append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.qty,
                    'name': line.product_id.name,
                  }))

                invoice = self.env['account.move'].create(invoice_vals)
                return_order.write({
                    'invoice_id': invoice.id

                  })






class SaleOrderLines(models.Model):
    _name = 'sale.order.return.lines'

    return_id = fields.Many2one('sale.order.return',readonly=1)
    product_id = fields.Many2one('product.product', string='Product',readonly=1 )
    original_qty = fields.Float(string='Original Quantity', readonly=True)
    qty = fields.Float(string='Return Quantity', default=0.0)
    # onhand_qty = fields.Float(string="الكمية المتاحة")
    delivered_qty = fields.Float(readonly=1,string='الكمية المسلمة')
    returned_qty = fields.Float(readonly=1,string= 'الكمية المرجعة مسبقًا')
    available_return_qty = fields.Float(string='الكمية المتاحة للإرجاع', readonly=1)
    product_uom = fields.Many2one('uom.uom', 'Units',readonly=1)
    price_unit=fields.Float('Price',readonly=1)

