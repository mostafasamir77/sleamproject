from odoo import fields, models,api
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class AccountMove(models.Model):
    _inherit = 'account.move'

    installments_ids = fields.One2many('account.installments', 'account_move_id')

    installment_number = fields.Integer(tracking=True, default=1)
    first_installment_date = fields.Date(tracking=True, required=True, default=fields.Date.today())
    advance_amount_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed_amount', 'Fixed Amount'),
    ], default='fixed_amount', required=True, tracking=True)
    advance_amount_value = fields.Float(tracking=True)


    calculated_advance_amount = fields.Float(compute='_compute_calculated_advance_amount', store=True)

    paid_advance_amount = fields.Float(tracking=True,readonly=True)

    remaining_advance_amount = fields.Float(compute='_compute_remaining_advance_amount',store=True)

    installment_value = fields.Float(tracking=True, compute='_compute_installment_value')

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


    @api.depends('invoice_line_ids.price_subtotal', 'advance_amount_value', 'advance_amount_type' , 'installment_number')
    def _compute_installment_value(self):
        """ calculate the value of each installment based on the advance amount and the installments number  """
        total_amount = sum(self.invoice_line_ids.mapped('price_subtotal'))

        for rec in self:
            try:
                rec.installment_value = (total_amount - rec.calculated_advance_amount) / rec.installment_number
            except:
                raise UserError("installment number must be grater than zero")
            

    def create_installments_lines(self):
        """ this method create the installments lines """
    
        for rec in self:
            i = 0
            installment_date = rec.first_installment_date
            while i < rec.installment_number:
                self.env['account.installments'].create({
                    'account_move_id': rec.id,
                    'date': installment_date,
                    'name': f"{i + 1}/{rec.installment_number}",
                    'amount': rec.installment_value,
                })
                installment_date += relativedelta(months=1)
                i += 1

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

        if 'first_installment_date' in vals or 'installment_number' in vals or 'vehicle_price' in vals or 'advance_amount_type' in vals or 'advance_amount_value' in vals:
            for rec in self:
                rec.installments_ids.unlink()  
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



class Installments(models.Model):
    _name = 'account.installments'

    account_move_id = fields.Many2one('account.move', ondelete='cascade')

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