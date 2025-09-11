from odoo import models

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def unlink(self):
        for payment in self:
            # Get invoices that were reconciled with this payment
            for invoice in payment.reconciled_invoice_ids:
                # Get installment lines for this invoice
                installments = self.env['account.installments'].search([
                    ('account_move_id', '=', invoice.id)
                ], order="date desc")  # latest installments first

                remaining = payment.amount
                for inst in installments:
                    if remaining <= 0:
                        break
                    if inst.paid_amount > 0:
                        # Deduct from the installment (starting from the end)
                        deduction = min(inst.paid_amount, remaining)
                        inst.sudo().paid_amount -= deduction
                        remaining -= deduction
        return super().unlink()