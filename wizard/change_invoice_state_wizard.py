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
            # 'paid_amount' : min(self.account_move_id.amount_total - self.account_move_id.amount_residual , self.deduct),
            'state' : 'due' ,
        })

        return created_installment
        
    def create_invoice_for_return(self):

        all_products = self.products_in_invoice
        selected_products = self.targeted_products_ids

        remaining_products = (all_products - selected_products) if self.change_type == 'return' else ( (all_products - selected_products) + self.new_product_ids )

        # build invoice lines for the targeted products
        invoice_lines = []
        for product in remaining_products:
            # find the matching line in the old invoice to copy quantity and price
            
            old_line = self.account_move_id.invoice_line_ids.filtered(
                lambda l: l.product_id == product
            )[:1]  # take first match if multiple
            if old_line :
                invoice_lines.append((0, 0, {
                    'product_id': product.id,
                    'quantity': old_line.quantity,
                    'price_unit': old_line.price_unit,
                    'tax_ids': [(6, 0, old_line.tax_ids.ids)],
                    'name': old_line.name or product.name,
                }))
            else:
                invoice_lines.append((0, 0, {
                    'product_id': product.id,
                    # 'name': old_line.name or product.name,
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

    def adding_deduction_product(self):
        # reset the invoice to draft state 
        self.account_move_id.button_draft()
        # delete the invoice lines 
        selected_products = self.targeted_products_ids.mapped('name')
        products_str = ", ".join(selected_products)

        note = {
                'move_id': self.account_move_id.id,
                'display_type': 'line_note',
                'name': f"{self.account_move_id.partner_id.name} is {self.change_type}: {products_str} ",
            }

        line = {
                'move_id': self.account_move_id.id,
                'product_id': self.env['product.product'].search([('id','=',5)], limit=1).id,
                'quantity': 1.0,
                'price_unit': self.deduct,
            }

        self.account_move_id.invoice_line_ids.unlink()
        # create the note and the line 
        self.env['account.move.line'].create([note,line])

        self.account_move_id.action_post()

    def reconcile_logic(self):
        # Get invoice receivable line
        invoice_line = self.account_move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )

        payments = self.env['account.payment'].search([
            ('partner_id', '=', self.account_move_id.partner_id.id),
            ('payment_type', '=', 'inbound'),
        ]).filtered(lambda p: not (p.move_id.has_reconciled_entries))

        # Get payment receivable line
        payment_lines = payments.mapped('move_id.line_ids').filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )

        # Reconcile them
        lines_to_reconcile = invoice_line | payment_lines
        if lines_to_reconcile:
            lines_to_reconcile.reconcile()

    def action_confirm(self):

        if self.change_type == 'return' :

            if set(self.targeted_products_ids.ids) == set(self.account_move_id.invoice_line_ids.mapped('product_id').ids) :

                if self.account_move_id.total_paid_amount == self.deduct :
                    print("from total_paid_amount == deduct ")
                # elif self.account_move_id.total_paid_amount > self.deduct :
                #     installment_id.sudo().customer_due_amount = self.account_move_id.total_paid_amount - self.deduct

            else :
                # create the invoice 
                invoice = self.create_invoice_for_return()
                # mark the invoice as copied 
                invoice.is_copy = True
                # assign value to old invoice id to indicates for old invoice 
                invoice.old_invoice_id = self.account_move_id.id
                # assign value to created invoice id to indicates for new invoice 
                self.account_move_id.created_invoice_id = invoice.id
        else:
            if self.new_product_ids :
                # create the invoice 
                invoice = self.create_invoice_for_return()
                # mark the invoice as copied 
                invoice.is_copy = True
                # assign value to old invoice id to indicates for old invoice 
                invoice.old_invoice_id = self.account_move_id.id
                # assign value to created invoice id to indicates for new invoice 
                self.account_move_id.created_invoice_id = invoice.id
            else :
                raise ValidationError("you have to to put at least one product in new products field")


        # to mark this invoice as used this button 
        self.account_move_id.is_returned_or_replaced = True


        self.account_move_id.advance_amount_value = 0

        # delete all old installments
        self.account_move_id.installments_ids.sudo().unlink()
        
        # adding invoice lines to describe what happen and the to adjust the invoice amount  
        self.adding_deduction_product()
        
        # creating the deduction installment
        installment_id = self.create_deduction_installment()

        # reconcile 
        self.reconcile_logic()

