from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    deduct_product = fields.Many2one(
        'product.product',
        string="Deduct Product",
        config_parameter='installments.deduct',
        help="Select the product to use for deduct"
    )