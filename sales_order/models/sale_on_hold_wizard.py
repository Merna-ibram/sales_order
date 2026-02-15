from odoo import models, fields, api
from datetime import datetime, timedelta

class OnHoldWizard(models.TransientModel):
    _name = 'sale.order.on.hold.wizard'
    _description = 'Sale On Hold Wizard'

    order_id = fields.Many2one('sale.order', string='Order', required=True)
    customer_name = fields.Char(related='order_id.partner_id.name', string='Customer')
    hold_date = fields.Date(string='تاريخ المتابعة', required=True)
    hold_time = fields.Selection(
        [(f"{h}:{m} AM", f"{h}:{m} AM") for h in range(1, 13) for m in ["00", "15", "30", "45"]] +
        [(f"{h}:{m} PM", f"{h}:{m} PM") for h in range(1, 13) for m in ["00", "15", "30", "45"]],
        string="وقت المتابعة",
        required=True
    )
    reason = fields.Text(string='سبب الانتظار')
    notes = fields.Text(string='ملاحظات')

    @api.model
    def default_get(self, fields_list):
        """تعيين القيم الافتراضية والتحقق من حالة الطلب"""
        res = super().default_get(fields_list)
        order_id = self.env.context.get('active_id')
        if order_id:
            order = self.env['sale.order'].browse(order_id)
            if order.state == 'sales_confirmed':
                raise models.ValidationError(
                    "⚠️ لا يمكن وضع الطلب On Hold لأنه تم تأكيده بالفعل"
                )
            res['order_id'] = order.id
        return res

    def action_set_on_hold(self):
        for wizard in self:
            order = wizard.order_id
            if order.state == 'sales_confirmed':
                order.message_post(body="⚠️ لا يمكن وضع الطلب On Hold لأنه تم تأكيده بالفعل")
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

            # تحديث حالة الطلب
            order.last_action_type = 'on_hold'
            order.attempt_date = fields.Datetime.now()
            order.attempts_count += 1

            # # إضافة سجل في الرسائل
            # order.message_post(
            #     body=f"""
            #     <p><strong>تم وضع الطلب في الانتظار</strong></p>
            #     <ul>
            #         <li><strong>تاريخ المتابعة:</strong> {wizard.hold_date}</li>
            #         <li><strong>وقت المتابعة:</strong> {wizard.hold_time}</li>
            #         <li><strong>السبب:</strong> {wizard.reason}</li>
            #         <li><strong>الملاحظات:</strong> {wizard.notes or 'لا توجد'}</li>
            #     </ul>
            #     """,
            #     subject="Order On Hold"
            # )

            # جدولة التنبيه
            wizard._schedule_notification()

        # return (
        #     {
        #         'type': 'ir.actions.act_window_close'
        #     },
        #     {
        #     'type': 'ir.actions.client',
        #     'tag': 'display_notification',
        #     'params': {
        #         'title': 'تم بنجاح',
        #         'message': f'تم وضع الطلب {self.order_id.name} في الانتظار حتى {self.hold_date} الساعة {self.hold_time}',
        #         'type': 'success',
        #         'sticky': False,
        #     }
        # })
        return {
            'type': 'ir.actions.act_window_close',
            'tag': 'reload',
            'params': {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'تم بنجاح',
                    'message': f'تم وضع الطلب {self.order_id.name} في الانتظار حتى {self.hold_date} الساعة {self.hold_time}',
                    'type': 'success',
                    'sticky': False,
                }
            }
        }

    def _schedule_notification(self):
        """جدولة التنبيه قبل الوقت المحدد بـ 15 دقيقة"""
        notification_datetime_str = f"{self.hold_date} {self.hold_time}"
        notification_datetime = datetime.strptime(notification_datetime_str, "%Y-%m-%d %I:%M %p")
        notification_datetime -= timedelta(minutes=15)

        # إنشاء activity للتنبيه
        self.env['mail.activity'].create({
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
            'res_model_id': self.env['ir.model']._get('sale.order').id,
            'res_id': self.order_id.id,
            'user_id': self.env.user.id,
            'date_deadline': notification_datetime.date(),
            'summary': f'متابعة طلب On Hold - {self.order_id.name}',
            'note': f"""
                <p><strong>تذكير بمتابعة الطلب</strong></p>
                <ul>
                    <li><strong>العميل:</strong> {self.order_id.partner_id.name}</li>
                    <li><strong>الهاتف:</strong> {self.order_id.phone or 'غير محدد'}</li>
                    <li><strong>الوقت المحدد:</strong> {self.hold_time}</li>
                    <li><strong>السبب:</strong> {self.reason}</li>
                    <li><strong>الملاحظات:</strong> {self.notes or 'لا توجد'}</li>
                </ul>
            """,
        })

        # إنشاء Cron Job للتنبيه التلقائي (اختياري)
        self._create_cron_notification(notification_datetime)

    def _create_cron_notification(self, notification_datetime):
        """إنشاء مهمة مجدولة للتنبيه"""
        cron_vals = {
            'name': f'On Hold Notification - {self.order_id.name}',
            'model_id': self.env['ir.model']._get('sale.order').id,
            'state': 'code',
            'code': f"""
order = env['sale.order'].browse({self.order_id.id})
if order.exists() and order.state == 'on_hold':
    order.message_post(
        body="<p><strong>🔔 تنبيه: حان وقت متابعة الطلب On Hold</strong></p>",
        subject="On Hold Follow-up Reminder",
        partner_ids=[{self.env.user.partner_id.id}]
    )
    env['bus.bus']._sendone(
        env.user.partner_id,
        'simple_notification',
        {{
            'title': 'تذكير متابعة',
            'message': f'حان وقت متابعة الطلب {{order.name}} - {{order.partner_id.name}}',
            'type': 'warning',
            'sticky': True,
        }}
    )
            """,
            'interval_number': 1,
            'interval_type': 'minutes',
            'nextcall': notification_datetime,
            'active': True,
        }

        self.env['ir.cron'].create(cron_vals)


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def activity_feedback(self, feedback='done', **kwargs):
        res = super().activity_feedback(feedback=feedback, **kwargs)

        for activity in self:
            if activity.res_model == 'sale.order' and 'متابعة طلب On Hold' in (activity.summary or ''):
                if feedback == 'done' and activity.res_id:
                    order = self.env['sale.order'].browse(activity.res_id)
                    if order.exists():
                        order.state = 'sales_confirmed'
                        order.is_sales_confirmed = True
                        order.message_post(body="✅ تم تأكيد المبيعات تلقائياً بعد إغلاق الـ On Hold Activity")
        return res
