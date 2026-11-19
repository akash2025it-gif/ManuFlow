from django.urls import path
from . import views

urlpatterns = [
    # Universal dispatcher
    path('', views.dashboard_dispatcher, name='dashboard_home'),

    # Role-specific dashboard endpoints
    path('admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('sales/', views.salesman_dashboard_view, name='salesman_dashboard'),
    path('production/', views.production_dashboard_view, name='production_dashboard'),
    path('auditor/', views.auditor_dashboard_view, name='auditor_dashboard'),
    path('owner/', views.owner_dashboard_view, name='owner_dashboard'),
]
