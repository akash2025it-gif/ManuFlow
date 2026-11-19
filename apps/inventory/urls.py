from django.urls import path
from . import views

urlpatterns = [
    # Inventory & Procurement Dashboard
    path('', views.inventory_dashboard_view, name='inventory_dashboard'),

    # Purchase Orders
    path('purchase-orders/', views.purchase_order_list_view, name='purchase_order_list'),
    path('purchase-orders/new/', views.purchase_order_create_view, name='purchase_order_create'),
    path('purchase-orders/<int:pk>/', views.purchase_order_detail_view, name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/approve/', views.purchase_order_approve_view, name='purchase_order_approve'),

    # Goods Receipt Notes (GRN / Purchase Receipts)
    path('grn/', views.grn_list_view, name='grn_list'),
    path('grn/new/', views.grn_create_view, name='grn_create'),
    path('grn/<int:pk>/', views.grn_detail_view, name='grn_detail'),
    path('grn/<int:pk>/post/', views.grn_post_view, name='grn_post'),

    # Current Stock Balances & Low Stock Warnings
    path('stock-summary/', views.stock_summary_view, name='stock_summary'),

    # Traceable Stock Movement Ledger
    path('ledger/', views.stock_ledger_list_view, name='stock_ledger_list'),

    # Stock Adjustments & Physical Inventory Audits
    path('adjustments/', views.stock_adjustment_list_view, name='stock_adjustment_list'),
    path('adjustments/new/', views.stock_adjustment_create_view, name='stock_adjustment_create'),
    path('adjustments/<int:pk>/', views.stock_adjustment_detail_view, name='stock_adjustment_detail'),
    path('adjustments/<int:pk>/post/', views.stock_adjustment_post_view, name='stock_adjustment_post'),
]
