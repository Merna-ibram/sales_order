
from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)



class StockPicking(models.Model):
    _inherit = 'stock.picking'

    return_ref=fields.Char()

    def button_validate(self):
        sale_return_id=self.env['sale.order'].search([('name','=',self.sale_id.name)],limit=1)
        _logger.info(sale_return_id)
        for pro in self.move_ids_without_package:
            _logger.info(pro.product_id.id)
            if sale_return_id:
               for rec in sale_return_id:
                   for order in rec.order_line:
                       if order.product_template_id.id == pro.product_id.product_tmpl_id.id:
                           _logger.info('yes')
                           sale_return = self.env['sale.order.return'].search([('name', '=', self.return_ref)],
                                                                              order='id desc', limit=1)
                           sale_return.write({
                               'state':'confirm'
                           })
                           if order.return_qty > 0 and self.origin.startswith('Return'):
                               old_return_qty = order.return_qty
                               order.return_qty = old_return_qty + pro.quantity
                           elif self.origin.startswith('Return'):
                               order.return_qty = pro.quantity

        return super(StockPicking, self).button_validate()
