from xml import etree

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
    num_pending = fields.Integer(string="Pending Orders", compute="_compute_order_stats", store=True)


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
        ('call_back', 'Call Back'),
        ('sales_confirm','Sales Confirm')
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
            order.num_pending = (
                    order.num_orders
                    - (order.num_cancelled + order.num_returned + order.num_delivered + order.num_replaced)
            )
    def write(self, vals):


            # لو في محاولة لتغيير الحالة
        # if 'state' in vals:
        #     for order in self:
        #         # لو الأوردر متأكد خلاص
        #         if order.state == 'sales_confirmed' and vals['state'] not in ['cancel', 'returned', 'replacement']:
        #             # نخلي الحالة زي ما هي، ونمنع التغيير
        #             vals['state'] = 'sales_confirmed'


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
            if order.state == 'sales_confirmed':
                raise models.ValidationError(
                    "⚠️ لا يمكن وضع الطلب No Answer لأنه تم تأكيده بالفعل"
                )
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'no_answer'
            order.message_post(body="🔴 No Answer")

    def action_on_hold(self):
        self.ensure_one()
        if self.state == 'sales_confirmed':
            self.message_post(body="⚠️ لا يمكن وضع الطلب On Hold لأنه تم تأكيده بالفعل")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'تنبيه',
                    'message': 'لا يمكن وضع الطلب On Hold لأنه تم تأكيده بالفعل',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        return {
            'name': 'Set Order On Hold',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.on.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id},
        }

    def action_call_back(self):
        for order in self:
            if order.state == 'sales_confirmed':
                order.message_post(body="⚠️ لا يمكن عمل Call Back لهذا الطلب لأنه تم تأكيده بالفعل")
                continue
            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'call_back'
            order.message_post(body="🟡 Call Back scheduled")

    def action_sales_confirm(self):


        for order in self:

            if order.state == 'sales_confirmed':
                raise models.ValidationError(
                    "⚠️ الطلب تم تأكيده بالفعل"
                )

            order.attempts_count += 1
            order.attempt_date = fields.Datetime.now()
            order.last_action_type = 'sales_confirm'

            old_state = order.state
            # تغيير الحالة
            if order.state != 'sale':
                order.state = 'sales_confirmed'
            order.is_sales_confirmed = True
            order.message_post(body=f"✅ {old_state} --> sales_confirmed")

            # تنفيذ Make Done لأي activity On Hold مرتبطة بالطلب
            on_hold_activities = self.env['mail.activity'].search([
                ('res_model', '=', 'sale.order'),
                ('res_id', '=', order.id),
                ('summary', 'like', 'متابعة طلب On Hold')
            ])
            on_hold_activities.action_done()  # تجعلهم Done مباشرة

            # إنشاء الـ picking لو مش موجود
            picking_exist = self.env['stock.picking'].search([('origin', '=', order.name)], limit=1)
            if not picking_exist:
                picking_vals = {
                    'partner_id': order.partner_id.id,
                    'picking_type_id': order.warehouse_id.out_type_id.id,
                    'location_id': order.warehouse_id.lot_stock_id.id,
                    'location_dest_id': order.partner_id.property_stock_customer.id,
                    'origin': order.name,
                    'sale_id': order.id,
                    'state': 'draft'
                }
                picking = self.env['stock.picking'].create(picking_vals)

                for line in order.order_line:
                    self.env['stock.move'].create({
                        'name': line.name,
                        'product_id': line.product_id.id,
                        'product_uom_qty': line.product_uom_qty,
                        'product_uom': line.product_uom.id,
                        'picking_id': picking.id,
                        'location_id': order.warehouse_id.lot_stock_id.id,
                        'location_dest_id': order.partner_id.property_stock_customer.id,
                    })
                order.warehouse_status = 'waiting_stock'

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

    # def _get_view(self, view_id=None, view_type='form', **options):
    #     arch, view = super()._get_view(view_id, view_type, **options)
    #
    #     if view_type == 'form':
    #         for node in arch.xpath("//button[@name='action_sales_confirm']"):
    #             node.set('string', 'Confirm Sales')
    #
    #
    #
    #     return arch, view

    def action_on_hold(self):
        """فتح wizard الـ On Hold"""
        return {
            'name': 'Set Order On Hold',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.on.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'active_id': self.id},
        }

    # def action_remove_on_hold(self):
    #     """إزالة الطلب من حالة On Hold"""
    #     self.ensure_one()
    #
    #     # إلغاء الأنشطة المجدولة
    #     activities = self.env['mail.activity'].search([
    #         ('res_model', '=', 'sale.order'),
    #         ('res_id', '=', self.id),
    #         ('summary', 'like', 'متابعة طلب On Hold')
    #     ])
    #     activities.unlink()
    #
    #     # إلغاء المهام المجدولة
    #     cron_jobs = self.env['ir.cron'].search([
    #         ('name', 'like', f'On Hold Notification - {self.name}')
    #     ])
    #     cron_jobs.unlink()
    #
    #     # تحديث حالة الطلب
    #     self.write({
    #         'state': 'draft',  # أو أي حالة مناسبة
    #         'hold_date': False,
    #         'hold_time': False,
    #         'hold_reason': False,
    #         'hold_notes': False,
    #         'last_action_type': 'removed_from_hold',
    #     })
    #
    #     self.message_post(
    #         body="<p><strong>تم إزالة الطلب من حالة الانتظار (On Hold)</strong></p>",
    #         subject="Removed from On Hold"
    #     )
    #
    #     return {
    #         'type': 'ir.actions.client',
    #         'tag': 'display_notification',
    #         'params': {
    #             'title': 'تم بنجاح',
    #             'message': f'تم إزالة الطلب {self.name} من حالة الانتظار',
    #             'type': 'success',
    #             'sticky': False,
    #         }
    #     }

    # @api.model
    # def check_on_hold_reminders(self):
    #     """دالة للتحقق من تذكيرات الـ On Hold (تستدعى بواسطة Cron)"""
    #     from datetime import datetime, timedelta
    #
    #     now = datetime.now()
    #
    #     # البحث عن الطلبات On Hold التي حان وقتها
    #     orders = self.search([
    #         ('state', '=', 'on_hold'),
    #         ('hold_date', '=', now.date()),
    #     ])
    #
    #     for order in orders:
    #         if order.hold_time:
    #             # تحويل hold_time إلى datetime
    #             hours = int(order.hold_time)
    #             minutes = int((order.hold_time - hours) * 60)
    #             hold_datetime = datetime.combine(order.hold_date, datetime.min.time())
    #             hold_datetime = hold_datetime.replace(hour=hours, minute=minutes)
    #
    #             # إذا حان الوقت (أو تجاوزه)
    #             if now >= hold_datetime:
    #                 # إرسال تنبيه
    #                 order.message_post(
    #                     body=f"""
    #                     <p><strong>🔔 تنبيه: حان وقت متابعة الطلب</strong></p>
    #                     <ul>
    #                         <li><strong>العميل:</strong> {order.partner_id.name}</li>
    #                         <li><strong>الهاتف:</strong> {order.phone or 'غير محدد'}</li>
    #                         <li><strong>السبب:</strong> {order.hold_reason}</li>
    #                     </ul>
    #                     """,
    #                     subject="On Hold Follow-up Time",
    #                 )
    #
    #                 # إنشاء activity للمتابعة
    #                 self.env['mail.activity'].create({
    #                     'activity_type_id': self.env.ref('mail.mail_activity_data_call').id,
    #                     'res_model_id': self.env['ir.model']._get('sale.order').id,
    #                     'res_id': order.id,
    #                     'user_id': self.env.user.id,
    #                     'date_deadline': fields.Date.today(),
    #                     'summary': f'متابعة طلب - {order.name}',
    #                     'note': f"""
    #                     <p><strong>حان وقت متابعة هذا الطلب</strong></p>
    #                     <ul>
    #                         <li><strong>العميل:</strong> {order.partner_id.name}</li>
    #                         <li><strong>الهاتف:</strong> {order.phone or 'غير محدد'}</li>
    #                         <li><strong>السبب:</strong> {order.hold_reason}</li>
    #                         <li><strong>الملاحظات:</strong> {order.hold_notes or 'لا توجد'}</li>
    #                     </ul>
    #                     """,
    #                 })

