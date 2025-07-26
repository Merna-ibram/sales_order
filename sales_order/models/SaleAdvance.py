# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleAdvancePaymentInvInherit(models.TransientModel):
    """وراثة نموذج sale.advance.payment.inv لإضافة ميزة دمج الفواتير"""
    _inherit = 'sale.advance.payment.inv'

    def create_invoices(self):
        """
        تعديل الدالة الأصلية لفحص وجود عملاء متعددين
        إذا كان هناك أكثر من عميل، يعرض wizard للدمج
        وإلا ينفذ السلوك الأصلي
        """
        self._check_amount_is_positive()

        # فحص إذا كان هناك أكثر من عميل واحد
        unique_partners = self.sale_order_ids.mapped('partner_id')
        if len(unique_partners) > 1:
            # عرض wizard لاختيار شركة الشحن
            return self._show_merge_invoice_wizard()

        # إذا كان عميل واحد فقط، تنفيذ السلوك الأصلي
        invoices = self._create_invoices(self.sale_order_ids)
        return self.sale_order_ids.action_view_invoice(invoices=invoices)

    def _show_merge_invoice_wizard(self):
        """
        عرض نافذة wizard لاختيار شركة الشحن وتأكيد دمج الفواتير
        """
        return {
            'name': _('دمج الفواتير - اختر شركة الشحن'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'sale.order.merge.invoice.wizard',
            'target': 'new',  # فتح في نافذة منبثقة
            'context': {
                'default_sale_order_ids': [(6, 0, self.sale_order_ids.ids)],
                'default_partner_ids': [(6, 0, self.sale_order_ids.mapped('partner_id').ids)],
            }
        }

    def create_merged_invoice(self, shipping_partner_id=None):
        """
        إنشاء فاتورة واحدة مدموجة من عدة أوامر بيع لعملاء مختلفين
        """
        self._check_amount_is_positive()

        # التحقق من أن جميع الطلبات صالحة للفوترة
        self._validate_orders_for_merging()

        # تحضير بيانات الفاتورة المدموجة
        invoice_vals = self._prepare_merged_invoice_vals(shipping_partner_id)

        # إنشاء الفاتورة
        invoice = self.env['account.move'].create(invoice_vals)

        # إضافة خطوط الفاتورة من جميع الطلبات
        self._add_invoice_lines_to_merged_invoice(invoice)

        # ربط الفاتورة بأوامر البيع
        self._link_invoice_to_orders(invoice)

        # إعادة حساب المبالغ والضرائب
        invoice._compute_tax_totals()
        invoice._compute_amount()

        # إرجاع عرض الفاتورة المنشأة
        return {
            'name': _('الفاتورة المدموجة'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': invoice.id,
            'target': 'current',
        }

    def _validate_orders_for_merging(self):
        """التحقق من صحة الطلبات للدمج"""
        # فحص حالة الطلبات
        invalid_orders = self.sale_order_ids.filtered(lambda o: o.state not in ['sale', 'done'])
        if invalid_orders:
            raise UserError(_('بعض الطلبات ليست في حالة صالحة للفوترة: %s') %
                            ', '.join(invalid_orders.mapped('name')))

        # فحص وحدة العملة
        currencies = self.sale_order_ids.mapped('currency_id')
        if len(currencies) > 1:
            raise UserError(_('لا يمكن دمج طلبات بعملات مختلفة. يرجى اختيار طلبات بنفس العملة.'))

    def _prepare_merged_invoice_vals(self, shipping_partner_id=None):
        """تحضير قيم الفاتورة المدموجة"""
        # تحديد العميل الرئيسي (شركة الشحن أو أول عميل)
        main_partner = self._get_main_partner(shipping_partner_id)

        # جمع أسماء جميع العملاء
        all_customers = self.sale_order_ids.mapped('partner_id')
        customer_names = ', '.join(all_customers.mapped('name'))

        return {
            'move_type': 'out_invoice',
            'partner_id': main_partner.id,
            'partner_shipping_id': main_partner.id,
            'invoice_date': fields.Date.context_today(self),
            'invoice_origin': ', '.join(self.sale_order_ids.mapped('name')),
            'company_id': self.sale_order_ids[0].company_id.id,
            'currency_id': self.sale_order_ids[0].currency_id.id,
            'team_id': self.sale_order_ids[0].team_id.id if self.sale_order_ids[0].team_id else False,
            'user_id': self.sale_order_ids[0].user_id.id if self.sale_order_ids[0].user_id else False,
            'narration': f'فاتورة مدموجة للعملاء: {customer_names}',
        }

    def _get_main_partner(self, shipping_partner_id):
        """الحصول على العميل الرئيسي للفاتورة"""
        if shipping_partner_id:
            return self.env['res.partner'].browse(shipping_partner_id)
        else:
            return self.sale_order_ids[0].partner_id

    def _add_invoice_lines_to_merged_invoice(self, invoice):
        """إضافة خطوط الفاتورة من جميع الطلبات"""
        for order in self.sale_order_ids:
            if order.state not in ['sale', 'done']:
                continue

            # الحصول على خطوط الطلب القابلة للفوترة
            sale_lines = order.order_line.filtered(
                lambda line: not line.display_type and line.qty_to_invoice > 0
            )

            for sale_line in sale_lines:
                # إعداد بيانات خط الفاتورة
                line_vals = self._prepare_invoice_line_from_sale_line(sale_line, order, invoice)

                # إنشاء خط الفاتورة
                self.env['account.move.line'].create(line_vals)

    def _prepare_invoice_line_from_sale_line(self, sale_line, order, invoice):
        """إعداد بيانات خط الفاتورة من خط الطلب"""
        # الحصول على الحساب المالي المناسب
        if sale_line.product_id:
            accounts = sale_line.product_id.product_tmpl_id._get_product_accounts()
            account = accounts['income'] or accounts['expense']
        else:
            # حساب افتراضي من الخصائص المالية للشركة
            account = self.env['account.account'].search([
                ('company_id', '=', invoice.company_id.id),
                ('account_type', '=', 'income')
            ], limit=1)

        # إعداد الاسم مع إضافة اسم العميل
        name = f"[{order.partner_id.name}] {sale_line.name}"

        # إعداد بيانات خط الفاتورة
        line_vals = {
            'move_id': invoice.id,
            'product_id': sale_line.product_id.id if sale_line.product_id else False,
            'name': name,
            'quantity': sale_line.qty_to_invoice,
            'price_unit': sale_line.price_unit,
            'discount': sale_line.discount,
            'account_id': account.id if account else False,
            'sale_line_ids': [(4, sale_line.id)],
            'tax_ids': [(6, 0, sale_line.tax_id.ids)],
            'product_uom_id': sale_line.product_uom.id if sale_line.product_uom else False,
        }

        # إضافة معلومات إضافية إذا كانت متوفرة
        if sale_line.analytic_distribution:
            line_vals['analytic_distribution'] = sale_line.analytic_distribution

        return line_vals

    def _link_invoice_to_orders(self, invoice):
        """ربط الفاتورة بأوامر البيع"""
        for order in self.sale_order_ids:
            # ربط الفاتورة بالطلب
            order.invoice_ids = [(4, invoice.id)]

            # تحديث كمية الفوترة في خطوط الطلب
            for order_line in order.order_line:
                if order_line.qty_to_invoice > 0:
                    # البحث عن خط الفاتورة المقابل
                    invoice_line = invoice.invoice_line_ids.filtered(
                        lambda l: order_line.id in l.sale_line_ids.ids
                    )
                    if invoice_line:
                        # تحديث الكمية المفوترة
                        order_line.qty_invoiced += invoice_line.quantity

    def _get_invoice_line_account(self, line_vals):
        """الحصول على الحساب المالي لخط الفاتورة - للتوافق مع النسخة القديمة"""
        if line_vals.get('product_id'):
            product = self.env['product.product'].browse(line_vals['product_id'])
            accounts = product.product_tmpl_id._get_product_accounts()
            return accounts['income'].id if accounts['income'] else False
        return False


# Wizard Model - يضاف في نفس الملف أو ملف منفصل
class SaleOrderMergeInvoiceWizard(models.TransientModel):
    """نافذة لاختيار شركة الشحن عند دمج الفواتير"""
    _name = 'sale.order.merge.invoice.wizard'
    _description = 'معالج دمج الفواتير'

    # الحقول الأساسية
    sale_order_ids = fields.Many2many(
        'sale.order',
        string='أوامر البيع',
        readonly=True
    )
    partner_ids = fields.Many2many(
        'res.partner',
        string='العملاء',
        readonly=True
    )
    shipping_partner_id = fields.Many2one(
        'res.partner',
        string='شركة الشحن/العميل الرئيسي',
        required=True,
        help="هذا العميل سيظهر كالعميل الرئيسي في الفاتورة المدموجة"
    )
    note = fields.Text(string='ملاحظات إضافية')

    # حقول للعرض والمعلومات
    total_amount = fields.Monetary(
        string='المبلغ الإجمالي',
        compute='_compute_total_amount'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        compute='_compute_currency'
    )
    orders_count = fields.Integer(
        string='عدد الطلبات',
        compute='_compute_counts'
    )
    customers_count = fields.Integer(
        string='عدد العملاء',
        compute='_compute_counts'
    )

    @api.depends('sale_order_ids')
    def _compute_total_amount(self):
        """حساب المبلغ الإجمالي للطلبات"""
        for record in self:
            record.total_amount = sum(record.sale_order_ids.mapped('amount_total'))

    @api.depends('sale_order_ids')
    def _compute_currency(self):
        """تحديد العملة المستخدمة"""
        for record in self:
            currencies = record.sale_order_ids.mapped('currency_id')
            record.currency_id = currencies[0] if len(currencies) == 1 else False

    @api.depends('sale_order_ids', 'partner_ids')
    def _compute_counts(self):
        """حساب عدد الطلبات والعملاء"""
        for record in self:
            record.orders_count = len(record.sale_order_ids)
            record.customers_count = len(record.partner_ids)

    @api.model
    def default_get(self, fields_list):
        """تعيين القيم الافتراضية عند فتح النافذة"""
        res = super().default_get(fields_list)

        # الحصول على البيانات من السياق
        context = self.env.context
        if context.get('default_sale_order_ids'):
            order_ids = context['default_sale_order_ids'][0][2]
            sale_orders = self.env['sale.order'].browse(order_ids)

            res['sale_order_ids'] = [(6, 0, sale_orders.ids)]
            res['partner_ids'] = [(6, 0, sale_orders.mapped('partner_id').ids)]

            # تعيين أول عميل كشركة شحن افتراضية
            if sale_orders:
                res['shipping_partner_id'] = sale_orders[0].partner_id.id

        return res

    def action_create_merged_invoice(self):
        """تنفيذ إنشاء الفاتورة المدموجة"""
        # التحقق من وجود طلبات
        if not self.sale_order_ids:
            raise UserError(_('لم يتم اختيار أي طلبات بيع!'))

        # التحقق من حالة الطلبات
        invalid_orders = self.sale_order_ids.filtered(
            lambda o: o.state not in ['sale', 'done']
        )
        if invalid_orders:
            raise UserError(_('بعض الطلبات ليست في حالة صالحة للفوترة: %s') %
                            ', '.join(invalid_orders.mapped('name')))

        # إنشاء wizard للـ sale.advance.payment.inv
        advance_wizard = self.env['sale.advance.payment.inv'].create({
            'sale_order_ids': [(6, 0, self.sale_order_ids.ids)],
            'advance_payment_method': 'delivered'  # أو أي قيمة مناسبة
        })

        # إنشاء الفاتورة المدموجة
        result = advance_wizard.create_merged_invoice(self.shipping_partner_id.id)

        # إضافة الملاحظات إذا كانت موجودة
        if self.note and result.get('res_id'):
            invoice = self.env['account.move'].browse(result['res_id'])
            current_narration = invoice.narration or ''
            new_narration = f"{current_narration}\n\nملاحظات إضافية:\n{self.note}"
            invoice.write({'narration': new_narration})

        return result

    def action_cancel(self):
        """إلغاء العملية وإغلاق النافذة"""
        return {'type': 'ir.actions.act_window_close'}

    @api.constrains('sale_order_ids')
    def _check_orders_currency(self):
        """التأكد من أن جميع الطلبات بنفس العملة"""
        for record in self:
            currencies = record.sale_order_ids.mapped('currency_id')
            if len(currencies) > 1:
                raise UserError(_('يجب أن تكون جميع أوامر البيع بنفس العملة ليتم دمجها.'))