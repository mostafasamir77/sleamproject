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
        domain="[('id','in', products_in_invoice)]",
        required=True
    )

    new_product_ids = fields.Many2many(
        'product.product',
        'rel_new_product',
        'invoice_button_id',
        'product_id',
        domain="[('id','not in', products_in_invoice)]"
    )
    
    deduct = fields.Float(string="Deduction Amount")

    @api.constrains('deduct')
    def deduct_validation(self):
        for rec in self:
            if rec.deduct <= 0 :
                raise ValidationError("Deduct Amount Must Be Grater Than Zero")

    
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
        
    def create_invoice_for_return(self):

        all_products = self.products_in_invoice
        selected_products = self.targeted_products_ids

        remaining_products = all_products - selected_products

        # build invoice lines for the targeted products
        invoice_lines = []
        for product in remaining_products:
            # find the matching line in the old invoice to copy quantity and price
            old_line = self.account_move_id.invoice_line_ids.filtered(
                lambda l: l.product_id == product
            )[:1]  # take first match if multiple

            invoice_lines.append((0, 0, {
                'product_id': product.id,
                'quantity': old_line.quantity,
                'price_unit': old_line.price_unit,
                'tax_ids': [(6, 0, old_line.tax_ids.ids)],
                'name': old_line.name or product.name,
            }))

        # create the new invoice
        invoice = self.env['account.move'].create({
            # 'contract_id': self.contract_wizard_id.id,  
            'move_type': 'out_invoice',
            'partner_id': self.account_move_id.partner_id.id,
            'journal_id': self.account_move_id.journal_id.id,
            'invoice_date': self.account_move_id.invoice_date,
            'invoice_line_ids': invoice_lines,
            'installment_number' : self.account_move_id.installment_number ,
        })

        return invoice


    def action_confirm(self):
        # to mark this invoice as used this button 
        self.account_move_id.is_returned_or_replaced = True

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

            else :
                invoice = self.create_invoice_for_return()
                self.account_move_id.created_invoice_id = invoice.id