# models/res_partner.py

from odoo import models, fields , api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
    ], string="Gender")


    def open_customer_statement(self):
        pass
