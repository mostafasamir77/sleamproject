from odoo import fields, models
from odoo.exceptions import UserError


class RegisterPaymentButton(models.TransientModel):
    _name = 'collect.advance.amount.button'

    account_move_id = fields.Many2one('account.move')

    journal_id = fields.Many2one('account.journal')
    amount = fields.Float(required=True)
    date = fields.Date(default=fields.Date.today(), required=True)
    payment_method_id = fields.Many2one('account.payment.method.line')


    def action_collect_advance_amount(self):
        amount_value = self.amount
        remaining = self.account_move_id.remaining_advance_amount
        
        if amount_value < 0 :
            raise UserError("The Amount Have to Be grater Than Zero")
        
        if amount_value > remaining :
            raise UserError(f"the amount you entered is bigger than the advance amount value: {remaining}")

        self.account_move_id.paid_advance_amount += amount_value

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
