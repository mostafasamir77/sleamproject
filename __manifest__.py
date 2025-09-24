{
    'name': 'Installments',
    'version': '18.1',
    'description': 'crate installments',
    'summary': '',
    'author': 'Mostafa Samir',
    'depends': [
        'base', 'account','purchase','invoice_stock_move'
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/installment_report.xml',
        'views/account_move_inherit_view.xml',
        'views/installments_view.xml',
        'views/account_payment_inherit_view.xml',
        'views/deduct_product_block.xml',
        'wizard/register_payment_wizard_view.xml',
        'wizard/collect_advance_amount_wizard_view.xml',
        'wizard/change_invoice_state_wizard_view.xml',        
    ],
    'auto_install': False,
    'application': True,
    'assets': {
        'web.report_assets_pdf': ['installments/static/src/css/font.css'],
    },
}