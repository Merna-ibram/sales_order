# -*- coding: utf-8 -*-
# from odoo import http


# class SalesOrderReturn(http.Controller):
#     @http.route('/sales_order_return/sales_order_return', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/sales_order_return/sales_order_return/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('sales_order_return.listing', {
#             'root': '/sales_order_return/sales_order_return',
#             'objects': http.request.env['sales_order_return.sales_order_return'].search([]),
#         })

#     @http.route('/sales_order_return/sales_order_return/objects/<model("sales_order_return.sales_order_return"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('sales_order_return.object', {
#             'object': obj
#         })

