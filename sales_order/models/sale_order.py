# models/sale_order.py

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
    attempt_date = fields.Date(string="Last Attempt Date", readonly=True)

    num_orders = fields.Integer(string="Total Orders", compute="_compute_order_stats", store=True)
    num_cancelled = fields.Integer(string="Cancelled Orders", compute="_compute_order_stats", store=True)
    num_returned = fields.Integer(string="Returned Orders", compute="_compute_order_stats", store=True)
    num_delivered = fields.Integer(string="Delivered Orders", compute="_compute_order_stats", store=True)

    state = fields.Selection(selection_add=[
        ('process', 'Processing'),
        ('sales_confirmed', 'Sales Confirmed'),
    ], default='process')

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

    def action_view_previous_orders(self):
        return {
            'name': 'Previous Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [('partner_id', '=', self.partner_id.id)],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_view_refunds(self):
        self.ensure_one()
        return {
            'name': 'Refunded Orders',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [
                ('partner_id', '=', self.partner_id.id),
                ('state', '=', 'returned')
            ],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_no_answer(self):
        for order in self:
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'no_answer'

    def action_on_hold(self):
        for order in self:
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'on_hold'

    def action_call_back(self):
        for order in self:
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'call_back'

    def action_sales_confirm(self):
        for order in self:
            order.state = 'sales_confirmed'

    def action_confirm(self):
        pass
