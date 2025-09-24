from odoo import fields, models,api
from odoo.exceptions import UserError,ValidationError
from dateutil.relativedelta import relativedelta


class AccountMove(models.Model):
    _inherit = 'account.move'

    installments_ids = fields.One2many('account.installments', 'account_move_id')
    created_invoice_id = fields.Many2one('account.move')
    old_invoice_id = fields.Many2one('account.move')
    is_returned_or_replaced = fields.Boolean(default=False)
    is_copy = fields.Boolean(default=False)
    reconciled_payments_count = fields.Integer(compute='_compute_reconciled_payments_count')
    installment_count = fields.Integer(compute='_compute_installment_count')
    installment_number = fields.Integer(tracking=True, default=1)
    first_installment_date = fields.Date(tracking=True, required=True, default=fields.Date.today())
    first_installment_value = fields.Float()
    last_installment_value = fields.Float()
    advance_amount_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed_amount', 'Fixed Amount'),
    ], default='fixed_amount', required=True, tracking=True)
    advance_amount_value = fields.Float(tracking=True)


    calculated_advance_amount = fields.Float(compute='_compute_calculated_advance_amount', store=True)

    paid_advance_amount = fields.Float(tracking=True,readonly=True)

    remaining_advance_amount = fields.Float(compute='_compute_remaining_advance_amount',store=True)

    installment_value = fields.Float(tracking=True, compute='_compute_installment_value')

    # start totals fields

    total_amount = fields.Float(compute='_compute_totals', store=True)
    total_paid_amount = fields.Float(compute='_compute_totals', store=True)
    total_remaining = fields.Float(compute='_compute_totals', store=True)
    total_current_due_amount = fields.Float(compute='_compute_totals', store=True, string="Current Due Amount")

    paid_total = fields.Float(compute='_compute_paid_total', store=True)

    @api.depends('amount_total', 'amount_residual')
    def _compute_paid_total(self):
        """
        Compute paid total and trigger distribution when values change
        """
        for rec in self:
            # Calculate paid amount
            rec.paid_total = rec.amount_total - rec.amount_residual
            # Trigger distribution
            rec.distribute_paid_amount()


    @api.depends(
        'installments_ids',
        'installments_ids.amount',
        'installments_ids.paid_amount',
        'installments_ids.remaining',
        'installments_ids.state',
        'matched_payment_ids',
        'matched_payment_ids.amount',
        'matched_payment_ids.state',
        'paid_advance_amount',
    )  
    def _compute_totals(self):
        for rec in self:
            installments = rec.installments_ids
            installments_with_due_state = installments.filtered(lambda i: i.state == 'due')

            rec.total_amount = sum(installments.mapped('amount'))
            rec.total_paid_amount = sum(installments.mapped('paid_amount'))
            rec.total_remaining = sum(installments.mapped('remaining')) 
            rec.total_current_due_amount = sum(installments_with_due_state.mapped('remaining'))

    # end totals fields


    @api.depends('advance_amount_type', 'advance_amount_value')
    def _compute_calculated_advance_amount(self):
        """ calculate the advance amount value in case it percentage or fixed amount and store it in this field """
        for rec in self:
            if rec.advance_amount_type == 'fixed_amount' :
                rec.calculated_advance_amount = rec.advance_amount_value
            elif rec.advance_amount_type == 'percentage':
                rec.calculated_advance_amount = (rec.advance_amount_value / 100) * sum(self.invoice_line_ids.mapped('price_subtotal'))

    @api.depends('calculated_advance_amount', 'paid_advance_amount')
    def _compute_remaining_advance_amount(self):
        """ this method compute the value of remaining advance amount """
        
        for rec in self:
            rec.remaining_advance_amount = rec.calculated_advance_amount - rec.paid_advance_amount


    @api.depends(
        'invoice_line_ids.price_subtotal',
        'advance_amount_value',
        'advance_amount_type',
        'installment_number',
        'first_installment_value',
        'last_installment_value',
        'amount_tax',
    )
    def _compute_installment_value(self):
        """Calculate the value of each installment."""
        for rec in self:
            # Ensure valid installment number
            if rec.installment_number <= 0:
                raise UserError("Installment number must be greater than zero")

            # Total invoice amount
            total_amount = rec.amount_total

            # Deduct advance amount + first + last installments
            first = rec.first_installment_value or 0.0
            last = rec.last_installment_value or 0.0
            advance = rec.calculated_advance_amount or 0.0

            remaining = total_amount - advance - first - last

            # How many installments are left for equal distribution?
            if first > 0 and last > 0:
                divisor = rec.installment_number - 2
            elif first > 0 or last > 0:
                divisor = rec.installment_number - 1
            else:
                divisor = rec.installment_number

            # Prevent division by zero
            if divisor <= 0:
                raise UserError("Not enough installments to distribute the amount.")

            # Final value per installment
            rec.installment_value = remaining / divisor
            
    @api.depends('amount_residual')
    def _compute_reconciled_payments_count(self):
        for rec in self:
            reconciled_payments = rec.line_ids.mapped(
                    'matched_debit_ids.debit_move_id.payment_id'
                ) | rec.line_ids.mapped(
                    'matched_credit_ids.credit_move_id.payment_id'
                )
            rec.reconciled_payments_count = len(reconciled_payments)

    @api.depends('installments_ids')
    def _compute_installment_count(self):
        for rec in self:
            rec.installment_count = len(rec.installments_ids)

    def create_installments_lines(self):
        """Create installment lines for each record"""
        Installment = self.env['account.installments'].sudo()
        if self.move_type == 'out_invoice' :

            for rec in self:
                installment_date = rec.first_installment_date
                for i in range(rec.installment_number):
                    # Determine amount for this installment
                    if i == 0 and rec.first_installment_value > 0:
                        amount = rec.first_installment_value
                    elif i == rec.installment_number - 1 and rec.last_installment_value > 0:
                        amount = rec.last_installment_value
                    else:
                        amount = rec.installment_value

                    # Skip zero or negative installments
                    if amount <= 0:
                        installment_date += relativedelta(months=1)
                        continue

                    # Create the installment
                    Installment.create({
                        'account_move_id': rec.id,
                        'date': installment_date,
                        'name': f"{i + 1}/{rec.installment_number}",
                        'amount': amount,
                    })

                    installment_date += relativedelta(months=1)
        else:
            print("this is not invoice")

    def action_post(self):
        res = super().action_post()
        
        # Get invoice receivable line
        invoice_line = self.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )

        payments = self.env['account.payment'].search([
            ('partner_id', '=', self.partner_id.id),
            ('payment_type', '=', 'inbound'),
            ('state','in', ['in_process','paid'] )
        ]).filtered(lambda p: not (p.move_id.has_reconciled_entries))

        # Get payment receivable line
        payment_lines = payments.mapped('move_id.line_ids').filtered(
            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
        )

        # Reconcile them
        lines_to_reconcile = invoice_line | payment_lines
        if lines_to_reconcile:
            lines_to_reconcile.reconcile()

        return res


    def distribute_paid_amount(self):
        """
        Distribute payments to installments based on paid amount
        """
        for rec in self:
            # Calculate amount to distribute
            target_paid_total = rec.paid_total
            current_paid_total = rec.total_paid_amount + rec.paid_advance_amount
            amount_to_distribute = target_paid_total - current_paid_total
            
            print(f"Distributing amount: {amount_to_distribute}")
            
            if abs(amount_to_distribute) < 0.01:  # Float precision tolerance
                continue
            
            # Handle positive distribution (payments)
            if amount_to_distribute > 0:
                self._distribute_positive_amount(rec, amount_to_distribute)
            
            # Handle negative distribution (unreconciliation)
            else:
                self._distribute_negative_amount(rec, abs(amount_to_distribute))

    def _distribute_positive_amount(self, record, amount_to_distribute):
        """Distribute positive amount - pay advance first if applicable"""
        
        # First, handle advance payment if there's remaining advance amount
        if record.calculated_advance_amount > 0 and record.remaining_advance_amount > 0:
            # Calculate how much we can apply to the advance
            advance_payment = min(record.remaining_advance_amount, amount_to_distribute)
            
            if advance_payment > 0:
                # Apply payment to advance amount
                record.paid_advance_amount += advance_payment
                amount_to_distribute -= advance_payment
                print(f"Applied {advance_payment} to advance payment. Remaining to distribute: {amount_to_distribute}")
        
        # If there's still amount to distribute after handling advance, distribute to installments
        if amount_to_distribute > 0:
            # Get installments in order (oldest first)
            installments = record.installments_ids.sorted(key=lambda r: r.date or r.create_date)
            
            for line in installments:
                if amount_to_distribute <= 0:
                    break
                    
                if line.payment_state != 'fully_paid':
                    # Calculate available amount in this installment
                    available = line.amount - line.paid_amount
                    payment_amount = min(available, amount_to_distribute)
                    
                    if payment_amount > 0:
                        # Update installment
                        line.sudo().write({
                            'paid_amount': line.paid_amount + payment_amount
                        })
                        amount_to_distribute -= payment_amount
                        
                        # Update installment state based on payment status
                        line.automated_action_check_installments_state()
                        print(f"Applied {payment_amount} to installment {line.name}. Remaining: {amount_to_distribute}")

    def _distribute_negative_amount(self, record, amount_to_reduce):
        """Distribute negative amount - reduce installments completely first, then advance"""
        
        # First, try to reduce installments as much as possible
        installments = record.installments_ids.sorted(
            key=lambda r: r.date or r.create_date, 
            reverse=True
        )
        
        for line in installments:
            if amount_to_reduce <= 0:
                break

            if line.paid_amount > 0:
                reduction = min(line.paid_amount, amount_to_reduce)
                line.sudo().write({
                    'paid_amount': line.paid_amount - reduction
                })
                amount_to_reduce -= reduction
                line.automated_action_check_installments_state()
                print(f"Reduced {reduction} from installment {line.name}. Remaining to reduce: {amount_to_reduce}")
        
        # Only reduce advance if all installments have been reduced to zero
        if amount_to_reduce > 0 and record.paid_advance_amount > 0:
            # Check if all installments are at zero
            total_installment_paid = sum(record.installments_ids.mapped('paid_amount'))
            if total_installment_paid == 0:
                reduction_from_advance = min(record.paid_advance_amount, amount_to_reduce)
                record.paid_advance_amount -= reduction_from_advance
                amount_to_reduce -= reduction_from_advance
                print(f"Reduced {reduction_from_advance} from advance payment. Remaining to reduce: {amount_to_reduce}")
            else:
                print(f"Cannot reduce advance payment until all installments are zero. Installments still have: {total_installment_paid}")
                
    @api.model
    def create(self, vals):
        """Create method - receives vals dict, returns created record"""
        record = super().create(vals)  # This returns the created record
        record.create_installments_lines()  # Call on the actual record
        return record
    
    @api.model
    def write(self, vals):
        res = super().write(vals)

        tracked_fields = {
            'first_installment_date',
            'installment_number',
            'advance_amount_type',
            'advance_amount_value',
            'first_installment_value',
            'last_installment_value',
            'amount_total'
        }

        if tracked_fields.intersection(vals.keys()):
            for rec in self:
                rec.installments_ids.sudo().unlink()
                rec.create_installments_lines()

        return res


    def action_pay_advance_amount(self):
        """ Open wizard view """

        action = self.env['ir.actions.actions']._for_xml_id('installments.collect_advance_amount_button_wizard_action')
        action['context'] = {'default_account_move_id' : self.id}
        return action



    def register_payment_action(self):
        """ Open wizard view """

        action = self.env['ir.actions.actions']._for_xml_id('installments.register_payment_button_wizard_action')
        action['context'] = {'default_account_move_id' : self.id}
        return action


    def change_invoice_state_action(self):
        """ Open wizard view """

        action = self.env['ir.actions.actions']._for_xml_id('installments.change_invoice_state_button_wizard_action')
        action['context'] = {
                'default_account_move_id' : self.id,
                'default_products_in_invoice' : self.invoice_line_ids.mapped('product_id').ids,
            }
        return action




    def open_related_installments(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Installments',
            'res_model': 'account.installments',
            'view_mode': 'list,form',
            'domain': [
                ('account_move_id', '=', self.id),
            ],
            'target': 'current',
        }
    
    def open_created_invoice(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'res_id': self.created_invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }    
        
    def open_old_invoice(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'res_id': self.old_invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


    def open_reconciled_payments(self):
        self.ensure_one()

        for rec in self:
            reconciled_payments = rec.line_ids.mapped(
                    'matched_debit_ids.debit_move_id.payment_id'
                ) | rec.line_ids.mapped(
                    'matched_credit_ids.credit_move_id.payment_id'
                )
        
            return reconciled_payments._get_records_action()



    def test_button(self):
        for rec in self:
            # Get reconciled payments
            reconciled_payments = rec.line_ids.mapped(
                'matched_debit_ids.debit_move_id.payment_id'
            ) | rec.line_ids.mapped(
                'matched_credit_ids.credit_move_id.payment_id'
            )

            payments = self.env['account.payment'].search([
                ('partner_id', '=', rec.partner_id.id),
                ('payment_type', '=', 'inbound'),
            ]).filtered(lambda p: not (p.move_id.has_reconciled_entries))
            # Get the payments from the move lines


            # Get unreconciled payments (simple version)
            unreconciled_payments = payments

            print(f"Reconciled payments: {reconciled_payments}")
            print("#" * 50)
            print(f"Unreconciled payments: {unreconciled_payments}")
            print("=" * 80)



class Installments(models.Model):
    _name = 'account.installments'

    account_move_id = fields.Many2one('account.move', ondelete='cascade')

    partner_id = fields.Many2one('res.partner', related='account_move_id.partner_id', string="Customer")

    date = fields.Date()
    name = fields.Char()
    amount = fields.Float()
    paid_amount = fields.Float()
    remaining = fields.Float(compute='_compute_remaining', store=True)
    payment_state = fields.Selection([
        ('not_paid','Not Paid'),
        ('partial','Partial'),
        ('fully_paid','Fully Paid'),
    ], compute='_compute_payment_state', store=True)
    state = fields.Selection([
        ('not_yet_due','Not Yet Due'),
        ('due','Due'),
        ('late','Late'),
        ('done','Done'),
    ],default="not_yet_due")


    def automated_action_check_installments_state(self):
        today = fields.Date.today()
        for line in self.env['account.installments'].search([]):
            if line.remaining == 0:
                line.state = 'done'
            elif line.date > today:
                line.state = 'not_yet_due'
            elif line.date == today:
                line.state = 'due'
            elif line.date < today:
                line.state = 'late'  

    @api.depends('amount', 'paid_amount')
    def _compute_remaining(self):
        """ this method calculate the remaining amount   """

        for rec in self:
            rec.remaining = rec.amount - rec.paid_amount


    @api.depends('remaining', 'amount', 'paid_amount')
    def _compute_payment_state(self):
        for rec in self:
            if rec.paid_amount == 0 :
                rec.payment_state = 'not_paid'
            elif rec.amount == rec.paid_amount:
                rec.payment_state = 'fully_paid'
            else:
                rec.payment_state = 'partial'

