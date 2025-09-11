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

    
    def create_deduction_installment(self):
        """ create one installment to the closing the invoice  """

        created_installment = self.env['account.installments'].sudo().create({
            'account_move_id' : self.account_move_id.id ,
            'date' : fields.Date.today() ,
            'name' : 'Deduction' ,
            'amount' : self.deduct ,
            'paid_amount' : min(self.account_move_id.total_paid_amount , self.deduct),
            'state' : 'due' ,
        })

        return created_installment
        
    # def create_invoice(self):
    #     self.env['account.move'].create({
    #         'move_type' : 'out_invoice',
    #         'partner_id' : self.account_move_id.partner_id.id ,
    #         ''
    #     })

    def action_confirm(self):
        # delete all old installments
        self.account_move_id.installments_ids.sudo().unlink()
        
        # creating the deduction installment
        installment_id = self.create_deduction_installment()

        if self.change_type == 'return' :

            if set(self.targeted_products_ids.ids) == set(self.account_move_id.invoice_line_ids.mapped('product_id').ids) :

                if self.account_move_id.total_paid_amount == self.deduct :
                    self.account_move_id.button_cancel()
            
                elif self.account_move_id.total_paid_amount > self.deduct :
                    installment_id.sudo().customer_due_amount = self.account_move_id.total_paid_amount - self.deduct

        