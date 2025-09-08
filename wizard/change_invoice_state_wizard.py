from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

class ChangeInvoiceState(models.TransientModel):
    _name = 'change.invoice.state.button'
    _description = 'Change Invoice State Wizard'

    account_move_id = fields.Many2one('account.move', string="Invoice")
    change_type = fields.Selection([
        ('return', 'Return'),
        ('replace', 'Replace'),
    ], default='return', required=True, string="Action Type")
    
    products_in_invoice = fields.Many2many(
        'product.product',
        'rel_products_in_invoice',
        'invoice_button_id',
        'product_id',
        string="Products in Invoice",
        readonly=True,
    )

    targeted_products_ids = fields.Many2many(
        'product.product',
        'rel_targeted_products',
        'invoice_button_id',
        'product_id',
        string="Targeted Products",
        domain="[('id','in', products_in_invoice)]"
    )

    new_product_ids = fields.Many2many(
        'product.product',
        'rel_new_product',
        'invoice_button_id',
        'product_id',
        domain="[('id','not in', products_in_invoice)]"
    )
    
    deduct = fields.Float(string="Deduction Amount")
    

    def action_confirm(self):
        if self.change_type == 'return' :

            pass
            
            # self.env['account_move'].create({
            #     'move_type': 'out_invoice' ,
            #     # 'd': ,
            # }) 
        