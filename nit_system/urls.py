"""
URL configuration for nit_system (NIT Trichy Order-to-Audit Management System).
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Global System Administration branding
admin.site.site_header = "ManuFlow Administration"
admin.site.site_title = "ManuFlow Admin"
admin.site.index_title = "System Management & Auditing Portal"

urlpatterns = [
    # Django Admin Portal
    path('admin/', admin.site.urls),

    # Core System Views (Landing, Public Info)
    path('', include('apps.core.urls')),

    # User Authentication & Role Management
    path('accounts/', include('apps.accounts.urls')),

    # Role-Based Workspaces & Dashboards
    path('dashboard/', include('apps.dashboard.urls')),

    # Master Data Management (Products, Pack Sizes, Customers, Suppliers, Materials, UOM, BOM)
    path('master-data/', include('apps.master_data.urls')),

    # Inventory & Purchase Management (PO, GRN, Stock Balances, Traceable Ledger, Adjustments)
    path('inventory/', include('apps.inventory.urls')),

    # Production Management (BOM Execution, Runs, Variances, Costing, Alerts)
    path('production/', include('apps.production.urls')),

    # Sales Management (Orders, GST Invoicing, PDF, Dispatch, Payment Tracking)
    path('sales/', include('apps.sales.urls')),

    # Accounts, Receivables, GST Reports & Data Exports
    path('finance/', include('apps.finance.urls')),
]

# Static & Media serving during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Custom Error Handlers
handler403 = 'apps.core.views.custom_403_view'
handler404 = 'apps.core.views.custom_404_view'
handler500 = 'apps.core.views.custom_500_view'
