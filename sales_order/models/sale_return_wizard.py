from odoo import models, fields, api
from odoo.exceptions import UserError

class ReturnWizard(models.TransientModel):
    _name = 'return.wizard'
    _description = 'Return Order Wizard'

    user_id = fields.Many2one('res.users', string='المستخدم', default=lambda self: self.env.user)
    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    return_reason = fields.Text(string='Return Reason')
    return_line_ids = fields.One2many('return.wizard.line', 'wizard_id', string='Return Lines')
    date_return = fields.Date(string="تاريخ الإرجاع", default=fields.Date.context_today)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'sale.order' and self.env.context.get('active_id'):
            sale_order = self.env['sale.order'].browse(self.env.context['active_id'])
            res['sale_order_id'] = sale_order.id
            res['return_line_ids'] = [(0, 0, {
                'product_id': line.product_id.id,
                'original_qty': line.product_uom_qty,
                'return_qty': line.product_uom_qty,
                'sale_line_id': line.id,
            }) for line in sale_order.order_line]
        return res

    def action_submit_return(self):
        self.ensure_one()
        sale_order = self.sale_order_id

        # التحقق من وجود عملية تسليم مكتملة
        original_picking = self.env['stock.picking'].search([
            ('origin', '=', sale_order.name),
            ('state', '=', 'done')
        ], limit=1)

        if not original_picking:
            raise UserError("لا يمكن إرجاع المنتجات لأن أمر التسليم لم يُنفذ بعد.")

        # تحديد نوع عملية الإرجاع (incoming) للمستودع
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id', '=', sale_order.warehouse_id.id)
        ], limit=1)

        if not picking_type:
            raise UserError("لم يتم العثور على نوع عملية الإرجاع (incoming) للمستودع.")

        # إنشاء الإرجاع
        return_picking = self.env['stock.picking'].create({
            'origin': f"Return - {sale_order.name}",
            'partner_id': sale_order.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': sale_order.partner_id.property_stock_customer.id,
            'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
            'move_type': 'direct',
        })

        move_ids = []
        for line in self.return_line_ids.filtered(lambda l: l.return_qty > 0 and l.product_id):
            if line.return_qty > line.original_qty:
                raise UserError(f"كمية الإرجاع لا يمكن أن تكون أكبر من الكمية الأصلية للمنتج {line.product_id.name}.")

            # التحقق من أن الكمية تم تسليمها بالفعل
            delivered_qty = sum(self.env['stock.move'].search([
                ('sale_line_id', '=', line.sale_line_id.id),
                ('state', '=', 'done')
            ]).mapped('quantity_done'))

            if delivered_qty <= 0:
                continue  # لم يتم تسليم هذا المنتج، لا يمكن إرجاعه

            move = self.env['stock.move'].create({
                'name': f"Return: {line.product_id.name}",
                'product_id': line.product_id.id,
                'product_uom_qty': line.return_qty,
                'product_uom': line.sale_line_id.product_uom.id,
                'picking_id': return_picking.id,
                'location_id': sale_order.partner_id.property_stock_customer.id,
                'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
            })
            move_ids.append(move.id)

        if not move_ids:
            return_picking.unlink()
            raise UserError("لم يتم إنشاء أي منتجات للإرجاع، برجاء التأكد من الكميات.")

        # تأكيد وتخصيص عملية الإرجاع
        return_picking.action_confirm()
        return_picking.action_assign()

        # زيادة عداد المرتجعات
        sale_order.num_returned += 1

        return {'type': 'ir.actions.act_window_close'}

    def _create_return_picking(self):
        sale_order = self.sale_order_id
        original_picking = self.env['stock.picking'].search([
            ('origin', '=', sale_order.name), ('state', 'in', ['done'])
        ], limit=1)

        if not original_picking:
            return

            # حدد نوع عملية الإرجاع المناسب
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'incoming'),
                ('warehouse_id', '=', sale_order.warehouse_id.id)
            ], limit=1)

            if not picking_type:
                raise UserError("لم يتم العثور على نوع عملية الإرجاع (incoming) للمستودع.")

        return_picking = self.env['stock.picking'].create({
            'partner_id': sale_order.partner_id.id,
            'picking_type_id': picking_type.id,
            'location_id': sale_order.partner_id.property_stock_customer.id,
            'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
            'origin': f"Return-{sale_order.name}",
            'state': 'draft'
        })

        move_ids = []
        for line in self.return_line_ids.filtered(lambda l: l.return_qty > 0 and l.product_id):
            move = self.env['stock.move'].create({
                'name': f"Return: {line.product_id.name}",
                'product_id': line.product_id.id,
                'product_uom_qty': line.return_qty,
                'product_uom': line.sale_line_id.product_uom.id,
                'picking_id': return_picking.id,
                'location_id': sale_order.partner_id.property_stock_customer.id,
                'location_dest_id': sale_order.warehouse_id.lot_stock_id.id,
            })
            move_ids.append(move.id)

        if not move_ids:
            return_picking.unlink()
            raise UserError("لم يتم إنشاء أي منتجات للإرجاع، برجاء التأكد من الكميات.")

        return_picking.action_confirm()
        return_picking.action_assign()


class ReturnWizardLine(models.TransientModel):
    _name = 'return.wizard.line'
    _description = 'Return Wizard Line'

    wizard_id = fields.Many2one('return.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Sale Line', readonly=True)
    original_qty = fields.Float(string='Original Quantity', readonly=True)
    return_qty = fields.Float(string='Return Quantity', default=0.0)
    # onhand_qty = fields.Float(string="الكمية المتاحة")
    delivered_qty = fields.Float(string='الكمية المسلمة', compute='_compute_delivery_return_qty')
    returned_qty = fields.Float(string='الكمية المرجعة مسبقًا', compute='_compute_delivery_return_qty')
    available_return_qty = fields.Float(string='الكمية المتاحة للإرجاع', compute='_compute_delivery_return_qty')

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
