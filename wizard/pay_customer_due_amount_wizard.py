from odoo import fields, models


class PayCustomerDueAmountButton(models.TransientModel):
    _name = 'pay.customer.due.amount.button'

    account_move_id = fields.Many2one('account.move')

    journal_id = fields.Many2one('account.journal')
    amount = fields.Float()
    date = fields.Date(default=fields.Date.today())
    payment_method_id = fields.Many2one('account.payment.method.line')

    def create_customer_due_amount_payment(self):
        self.ensure_one()

        # Ensure invoice is posted
        if self.account_move_id.state == 'draft':
            self.account_move_id.action_post()

        # Create the payment
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',  # money goes out
            'partner_type': 'customer',
            'partner_id': self.account_move_id.partner_id.id,
            'amount': self.amount,
            'date': self.date,
            'journal_id': self.journal_id.id,
            'payment_method_line_id': self.payment_method_id.id,
        })

        # Post the payment
        if payment.state == 'draft':
            payment.action_post()

        # Reconcile receivable lines between payment and invoice
        (
            payment.move_id.line_ids.filtered(
                lambda l: l.account_id == self.account_move_id.partner_id.property_account_receivable_id
            )
            | self.account_move_id.line_ids.filtered(
                lambda l: l.account_id == self.account_move_id.partner_id.property_account_receivable_id
            )
        ).reconcile()

        return payment

    def action_confirm_pay(self):
        installment_lines = self.account_move_id.installments_ids
        amount_value = self.amount

        for line in installment_lines :
            if amount_value <= 0:
                break

            # Calculate payment amount for this line
            payment_amount = min(line.remaining_customer_due_amount, amount_value)

            if payment_amount > 0:
                # Update amounts
                line.sudo().paid_customer_due_amount += payment_amount
                amount_value -= payment_amount

            if line.remaining_customer_due_amount == 0 :
                self.account_move_id.button_cancel()

        # create the payment 
        payment = self.create_customer_due_amount_payment()

        