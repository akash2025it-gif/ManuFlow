from django.urls import path
from . import views

urlpatterns = [
    # Sales Hub Dashboard
    path('', views.sales_dashboard_view, name='sales_hub'),

    # Sales Orders
    path('orders/', views.sales_order_list_view, name='sales_order_list'),
    path('orders/create/', views.sales_order_create_view, name='sales_order_create'),
    path('orders/<int:pk>/', views.sales_order_detail_view, name='sales_order_detail'),
    path('orders/<int:pk>/edit/', views.sales_order_edit_view, name='sales_order_edit'),
    path('orders/<int:pk>/submit/', views.sales_order_submit_view, name='sales_order_submit'),
    path('orders/<int:pk>/approve/', views.sales_order_approve_view, name='sales_order_approve'),
    path('orders/<int:pk>/reject/', views.sales_order_reject_view, name='sales_order_reject'),

    # GST Invoices
    path('invoices/', views.invoice_list_view, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail_view, name='invoice_detail'),
    path('invoices/<int:pk>/pdf/', views.invoice_pdf_view, name='invoice_pdf'),
    path('orders/<int:order_pk>/generate-invoice/', views.invoice_generate_view, name='invoice_generate'),

    # Dispatches & Stock Deduction
    path('dispatches/', views.dispatch_list_view, name='dispatch_list'),
    path('orders/<int:order_pk>/dispatch/', views.dispatch_create_view, name='dispatch_create'),

    # Payment Receipts
    path('invoices/<int:invoice_pk>/payment/', views.payment_record_create_view, name='payment_create'),
]
