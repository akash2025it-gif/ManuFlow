from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('audit/', views.audit_trail_view, name='audit_trail'),
    path('audit/<int:pk>/', views.audit_trail_detail_view, name='audit_trail_detail'),
]
