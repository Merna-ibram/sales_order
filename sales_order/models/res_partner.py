# models/res_partner.py

from odoo import models, fields , api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    phone2 = fields.Char(string="Phone 2")
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], string="Gender")
