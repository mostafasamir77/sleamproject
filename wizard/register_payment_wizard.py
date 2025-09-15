from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RegisterPaymentButton(models.TransientModel):
    _name = 'register.payment.button'

    account_move_id = fields.Many2one('account.move')

    journal_id = fields.Many2one('account.journal', domain="[('type','in', ('cash','bank') )]", required=True )
    amount = fields.Float()
    date = fields.Date(default=fields.Date.today(), required=True)
    payment_method_id = fields.Many2one('account.payment.method.line',required=True)

    def check_if_valid_amount(self):
        if self.amount > self.account_move_id.total_remaining :
            raise ValidationError(f"this amount are more than the actual remaining amount: {self.account_move_id.total_remaining}")



    def action_register_payment(self):
        # validation for the amount that user pay
        self.check_if_valid_amount()

        installment_lines = self.account_move_id.installments_ids
        amount_value = self.amount

        for line in installment_lines :
            if amount_value <= 0:
                break

            # Calculate payment amount for this line
            payment_amount = min(line.remaining, amount_value)


            if payment_amount > 0:
                # Update amounts
                line.sudo().paid_amount += payment_amount
                amount_value -= payment_amount


            if line.remaining == 0:
                line.sudo().state = 'done'

        # Create payment using the register payment wizard
        payment_wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=self.account_move_id.ids
        ).create({
            'journal_id': self.journal_id.id,
            'payment_method_line_id': self.payment_method_id.id,
            'amount': self.amount,
            'payment_date': self.date,
        })

        # Create the payment
        payments = payment_wizard.action_create_payments()

