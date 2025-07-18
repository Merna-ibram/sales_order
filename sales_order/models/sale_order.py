from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    phone = fields.Char(related='partner_id.phone', string="Phone", store=True)
    phone2 = fields.Char(related='partner_id.mobile', string='Phone 2', store=True, readonly=True)
    gender = fields.Selection(related='partner_id.gender', string='Gender', store=True, readonly=True)

    shipping_agent_id = fields.Many2one('res.partner', string="Shipping Agent")
    shipping_company = fields.Char(string="Shipping Company")
    tracking_number = fields.Char(string="Tracking Number")
    payment_type = fields.Selection([
        ('cod', 'Cash on Delivery'),
        ('prepaid', 'Prepaid')
    ], string="Payment Type")

    total_quantity = fields.Float(string="Total Quantity", compute="_compute_total_quantity", store=True)
    attempts_count = fields.Integer(string="Attempts Count", readonly=True)
    attempt_date = fields.Datetime(string="Last Attempt Date", readonly=True)

    num_orders = fields.Integer(string="Total Orders", compute="_compute_order_stats", store=True)
    num_cancelled = fields.Integer(string="Cancelled Orders", compute="_compute_order_stats", store=True)
    num_returned = fields.Integer(string="Returned Orders", compute="_compute_order_stats", store=True)
    num_delivered = fields.Integer(string="Delivered Orders", compute="_compute_order_stats", store=True)
    num_replaced = fields.Integer(string="Replaced Orders", compute="_compute_order_stats", store=True)

    state = fields.Selection(selection_add=[
        ('process', 'Processing'),
        ('returned', 'Returned'),
        ('replacement', 'Replacement'),
        ('sales_confirmed', 'Sales Confirmed'),
    ], default='process')
    is_sales_confirmed = fields.Boolean(string="Confirmed", default=False)

    warehouse_status = fields.Selection([
        ('pending', 'Pending'),
        ('waiting_stock', 'Waiting Stock'),
        ('ready_to_assign', 'Ready to Assign'),
        ('assigned_to_shipping', 'Assigned to Shipping'),
    ], string="Warehouse Status", default='pending', tracking=True, readonly=True)

    last_action_type = fields.Selection([
        ('no_answer', 'No Answer'),
        ('on_hold', 'On Hold'),
        ('call_back', 'Call Back')
    ], string="Last Action Type", readonly=True)

    @api.depends('order_line.product_uom_qty')
    def _compute_total_quantity(self):
        for order in self:
            order.total_quantity = sum(line.product_uom_qty for line in order.order_line)

    @api.depends('partner_id', 'state')
    def _compute_order_stats(self):
        for order in self:
            domain = [('partner_id', '=', order.partner_id.id)]
            all_orders = self.env['sale.order'].search(domain)
            order.num_orders = len(all_orders)
            order.num_cancelled = len(all_orders.filtered(lambda o: o.state == 'cancel'))
            order.num_returned = len(all_orders.filtered(lambda o: o.state == 'returned'))
            order.num_delivered = len(all_orders.filtered(lambda o: o.state in ['sale', 'done']))
            order.num_replaced = len(all_orders.filtered(lambda o: o.state == 'replacement'))

    def write(self, vals):
        state_changed = 'state' in vals
        res = super().write(vals)

        if state_changed:
            for order in self:
                if order.partner_id:
                    related_orders = self.env['sale.order'].search([
                        ('partner_id', '=', order.partner_id.id)
                    ])
                    related_orders._compute_order_stats()
                    for other in related_orders - order:
                        other.message_post(body=f"ℹ️ Status updated in another order for this customer.")

        return res

    def action_no_answer(self):
        for order in self:
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'no_answer'
            order.message_post(body="🔴 No Answer")

    def action_on_hold(self):
        for order in self:
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'on_hold'
            order.message_post(body="🟠 Order put On Hold")

    def action_call_back(self):
        for order in self:
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'call_back'
            order.message_post(body="🟡 Call Back scheduled")

    def action_sales_confirm(self):
        for order in self:
            old_state = order.state
            order.state = 'sales_confirmed'
            order.is_sales_confirmed = True
            order.message_post(body=f"✅ {old_state} --> sales_confirmed")

    def mark_as_returned(self):
        for rec in self:
            old_state = rec.state
            rec.write({'state': 'returned'})
            # rec.message_post(body="🔁 Changed from {} ➜ Returned".format(old_state))

    def mark_as_replacement(self):
        for rec in self:
            old_state = rec.state
            rec.write({'state': 'replacement'})
            # rec.message_post(body="🔁 Changed from {} ➜ Replacement".format(old_state))

    def mark_as_cancelled(self):
        for rec in self:
            if rec.state != 'cancel':
                old_state = rec.state
                rec.action_cancel()
                # rec.message_post(body="❌ Changed from {} ➜ Cancelled".format(old_state))

    def action_view_previous_orders(self):
        return {
            'name': 'Previous Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [('partner_id', '=', self.partner_id.id)],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_refunds(self):
        return {
            'name': 'Refunded Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('state', '=', 'returned'),
            ],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_replacements(self):
        return {
            'name': 'Replaced Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('state', '=', 'replacement'),
            ],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_view_cancelled_orders(self):
        return {
            'name': 'Cancelled Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [('partner_id', '=', self.partner_id.id), ('state', '=', 'cancel')],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_set_pending(self):
        for rec in self:
            if rec.warehouse_status != 'pending':
                rec.warehouse_status = 'pending'
                # rec.message_post(body="🕒 Warehouse Status ➜ Pending")

    def action_set_waiting_stock(self):
        for rec in self:
            if rec.warehouse_status != 'waiting_stock':
                rec.warehouse_status = 'waiting_stock'
                # rec.message_post(body="⏳ Warehouse Status ➜ Waiting Stock")

    def action_set_ready_to_assign(self):
        for rec in self:
            if rec.warehouse_status != 'ready_to_assign':
                rec.warehouse_status = 'ready_to_assign'
                # rec.message_post(body="📦 Warehouse Status ➜ Ready to Assign")

    def action_set_assigned_to_shipping(self):
        for rec in self:
            if rec.warehouse_status != 'assigned_to_shipping':
                rec.warehouse_status = 'assigned_to_shipping'
                # rec.message_post(body="🚚 Warehouse Status ➜ Assigned to Shipping")


