# -*- coding: utf-8 -*-
{
    'name': "salesorder",
    'author': "My Company",
    'website': "https://www.yourcompany.com",
    'version': '0.1',
    'license': 'LGPL-3',
    'application': True,
    'installable': True,
    'category': 'Healthcare',

    # 'post_init_hook': 'assign_country_codes_on_install',



    'depends': [
        'base','account', 'sale','sale_management', 'stock'
    ],

    'data': [
        # Security
        "security/ir.model.access.csv",



        # Data



        # Views
        'views/sales_views.xml',
        'views/partner_views.xml',
        'views/merge_invoice_wizard_view.xml',

        # Wizards


        # Reports


    ],


}
