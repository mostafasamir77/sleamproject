from odoo import models,fields

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_for_advance_amount = fields.Boolean(string="For Advance Amount", default=False)

    def installment_effect(self):
        for payment in self:
            # Get invoices that were reconciled with this payment
            for invoice in payment.reconciled_invoice_ids:
                # Get installment lines for this invoice
                installments = self.env['account.installments'].search([
                    ('account_move_id', '=', invoice.id)
                ], order="date desc")  # latest installments first

                if payment.is_for_advance_amount == True:
                    invoice.paid_advance_amount -= payment.amount
                    if invoice.paid_advance_amount == 0:
                        invoice.button_draft()
                else:
                    remaining = payment.amount
                    for inst in installments:
                        if remaining <= 0:
                            break
                        if inst.paid_amount > 0:
                            # Deduct from the installment (starting from the end)
                            deduction = min(inst.paid_amount, remaining)
                            inst.sudo().paid_amount -= deduction
                            remaining -= deduction

    # def unlink(self):
    #     self.installment_effect()
    #     return super().unlink()


    def custom_cancel_button(self):
        """ this button made for enable the user to cancel the payment directly if the payment 
            crated by register payment button to apply the installment logic """

        self.action_draft()
        self.action_cancel()
        self.installment_effect()