from odoo import models,fields

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_for_advance_amount = fields.Boolean(string="For Advance Amount", default=False)