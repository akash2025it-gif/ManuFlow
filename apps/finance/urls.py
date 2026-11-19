from django.urls import path
from . import views

app_name = 'finance'

urlpatterns = [
    # Command Center Dashboard
    path('', views.finance_dashboard_view, name='dashboard'),

    # Receivables & Overdue Management
    path('receivables/', views.receivables_summary_view, name='receivables_summary'),

    # Payment Vouchers & Payments Recording
    path('payments/', views.payments_list_view, name='payments_list'),
    path('payments/record/', views.payment_create_view, name='payment_create'),

    # GST Reports
    path('reports/gst-sales-register/', views.gst_sales_register_view, name='gst_sales_register'),
    path('reports/gst-monthly-summary/', views.gst_monthly_summary_view, name='gst_monthly_summary'),

    # Stock & Production Reports
    path('reports/stock-inventory/', views.stock_inventory_report_view, name='stock_report'),
    path('reports/stock-ledger/', views.stock_ledger_report_view, name='stock_ledger_report'),
    path('reports/production-variance/', views.production_variance_report_view, name='production_variance_report'),
    path('reports/sales-dispatch/', views.sales_dispatch_report_view, name='sales_dispatch_report'),

    # Data Exports (CSV & Excel)
    path('exports/sales-register/', views.export_sales_register_view, name='export_sales_register'),
    path('exports/receivables/', views.export_receivables_view, name='export_receivables'),
    path('exports/stock-summary/', views.export_stock_summary_view, name='export_stock_summary'),
    path('exports/stock-ledger/', views.export_stock_ledger_view, name='export_stock_ledger'),
]
