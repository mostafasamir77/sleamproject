from odoo import fields, models,api
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class AccountMove(models.Model):
    _inherit = 'account.move'

    installments_ids = fields.One2many('account.installments', 'account_move_id')
    created_invoice_id = fields.Many2one('account.move')
    is_returned_or_replaced = fields.Boolean()
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

    @api.depends(
        'installments_ids.amount',
        'installments_ids.paid_amount',
        'installments_ids.remaining',
        'installments_ids.state',
        'matched_payment_ids',
        'matched_payment_ids.amount',
        'matched_payment_ids.state',
    )  
    def _compute_totals(self):
        for rec in self:
            installments = rec.installments_ids
            installments_with_due_state = installments.filtered(lambda i: i.state == 'due')
            payments_with_paid_or_in_progress_state = rec.matched_payment_ids.filtered(lambda p: p.state in ['in_process', 'paid'] )

            rec.total_amount = sum(installments.mapped('amount')) + rec.calculated_advance_amount
            rec.total_paid_amount = sum(payments_with_paid_or_in_progress_state.mapped('amount'))
            rec.total_remaining = sum(installments.mapped('remaining')) + rec.remaining_advance_amount
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
    )
    def _compute_installment_value(self):
        """Calculate the value of each installment."""
        for rec in self:
            # Ensure valid installment number
            if rec.installment_number <= 0:
                raise UserError("Installment number must be greater than zero")

            # Total invoice amount
            total_amount = rec.amount_residual

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
            
    def create_installments_lines(self):
        """Create installment lines for each record"""
        Installment = self.env['account.installments'].sudo()

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

    def action_post(self):
        res = super().action_post()
        
        if self.remaining_advance_amount != 0:
            raise UserError(f"you have to pay advance amount first: {self.remaining_advance_amount}")

        return res


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
            'vehicle_price',
            'advance_amount_type',
            'advance_amount_value',
            'first_installment_value',
            'last_installment_value',
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

    customer_due_amount = fields.Float()
    paid_customer_due_amount = fields.Float()
    remaining_customer_due_amount = fields.Float(compute='_compute_remaining_customer_due_amount',store=True,string="Remaining Customer Due")


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

    @api.depends('customer_due_amount','paid_customer_due_amount')
    def _compute_remaining_customer_due_amount(self):
        """ this for compute the value of remaining_customer_due_amount if the customer will get mony back """

        for rec in self:
            rec.remaining_customer_due_amount = rec.customer_due_amount - rec.paid_customer_due_amount