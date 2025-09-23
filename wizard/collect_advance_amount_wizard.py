from odoo import fields, models,api
from odoo.exceptions import UserError


class RegisterPaymentButton(models.TransientModel):
    _name = 'collect.advance.amount.button'

    account_move_id = fields.Many2one('account.move')

    journal_id = fields.Many2one('account.journal',domain="[('type','in', ('cash','bank') )]", required=True)
    amount = fields.Float(required=True)
    date = fields.Date(default=fields.Date.today(), required=True)
    payment_method_id = fields.Many2one('account.payment.method.line',
                                        required=True,
                                        context={'hide_payment_journal_id': 1},
                                        domain="[('id', 'in', available_payment_method_line_ids)]")


    # This field comes from account.payment.register
    available_payment_method_line_ids = fields.Many2many(
        'account.payment.method.line',
        compute="_compute_available_payment_methods",
        string="Available Payment Methods",
    )

    @api.onchange('journal_id')
    def _compute_available_payment_methods(self):
        for rec in self:
            rec.available_payment_method_line_ids = self.journal_id.outbound_payment_method_line_ids

    def action_collect_advance_amount(self):

        amount_value = self.amount
        remaining = self.account_move_id.remaining_advance_amount
        
        if amount_value < 0 :
            raise UserError("The Amount Have to Be grater Than Zero")
        
        if amount_value > remaining :
            raise UserError(f"the amount you entered is bigger than the remaining advance amount value: {remaining}")

        # self.account_move_id.paid_advance_amount += amount_value

        # change the invoice to posted state
        if self.account_move_id.state == 'draft':
            self.account_move_id.action_post()
            
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
        payment = payment_wizard.action_create_payments()
        print(f"mostafa payment {payment}")

        self.env['account.payment'].browse(payment['res_id']).is_for_advance_amount = True 
