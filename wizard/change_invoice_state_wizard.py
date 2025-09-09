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

    total_paid_amount_for_installments = fields.Float()
    
    def create_deduction_installment(self):
        self.env['account.installments'].sudo().create({
            'account_move_id' : self.account_move_id.id ,
            'date' : fields.Date.today() ,
            'name' : 'Deduction' ,
            'amount' : self.deduct ,
            'paid_amount' : self.total_paid_amount_for_installments,
            'state' : 'due' ,
        })
        


    def action_confirm(self):
        # delete all old installments
        self.account_move_id.installments_ids.sudo().unlink()
        
        # creating the deduction installment
        self.create_deduction_installment()

        # if self.change_type == 'return' and  :


        