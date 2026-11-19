from django.urls import path
from . import views

urlpatterns = [
    # Master Data Central Hub
    path('', views.master_data_hub_view, name='master_data_hub'),

    # 1. Finished Products & Pack Sizes
    path('products/', views.product_list_view, name='product_list'),
    path('products/new/', views.product_create_view, name='product_create'),
    path('products/<int:pk>/', views.product_detail_view, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update_view, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete_view, name='product_delete'),
    path('products/<int:product_pk>/pack-sizes/new/', views.pack_size_create_view, name='pack_size_create'),
    path('pack-sizes/<int:pk>/edit/', views.pack_size_update_view, name='pack_size_update'),
    path('pack-sizes/<int:pk>/delete/', views.pack_size_delete_view, name='pack_size_delete'),

    # 2. Customers (Retailers and Distributors)
    path('customers/', views.customer_list_view, name='customer_list'),
    path('customers/new/', views.customer_create_view, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail_view, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update_view, name='customer_update'),
    path('customers/<int:pk>/delete/', views.customer_delete_view, name='customer_delete'),

    # 3. Suppliers
    path('suppliers/', views.supplier_list_view, name='supplier_list'),
    path('suppliers/new/', views.supplier_create_view, name='supplier_create'),
    path('suppliers/<int:pk>/', views.supplier_detail_view, name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', views.supplier_update_view, name='supplier_update'),
    path('suppliers/<int:pk>/delete/', views.supplier_delete_view, name='supplier_delete'),

    # 4. Raw Materials
    path('raw-materials/', views.raw_material_list_view, name='raw_material_list'),
    path('raw-materials/new/', views.raw_material_create_view, name='raw_material_create'),
    path('raw-materials/<int:pk>/', views.raw_material_detail_view, name='raw_material_detail'),
    path('raw-materials/<int:pk>/edit/', views.raw_material_update_view, name='raw_material_update'),
    path('raw-materials/<int:pk>/delete/', views.raw_material_delete_view, name='raw_material_delete'),

    # 5. Packaging Materials
    path('packaging-materials/', views.packaging_material_list_view, name='packaging_material_list'),
    path('packaging-materials/new/', views.packaging_material_create_view, name='packaging_material_create'),
    path('packaging-materials/<int:pk>/', views.packaging_material_detail_view, name='packaging_material_detail'),
    path('packaging-materials/<int:pk>/edit/', views.packaging_material_update_view, name='packaging_material_update'),
    path('packaging-materials/<int:pk>/delete/', views.packaging_material_delete_view, name='packaging_material_delete'),

    # 6. Units of Measurement & Conversions
    path('uom/', views.uom_list_view, name='uom_list'),
    path('uom/new/', views.uom_create_view, name='uom_create'),
    path('uom/<int:pk>/edit/', views.uom_update_view, name='uom_update'),
    path('uom/<int:pk>/delete/', views.uom_delete_view, name='uom_delete'),
    path('uom/conversions/new/', views.conversion_create_view, name='conversion_create'),
    path('uom/conversions/<int:pk>/delete/', views.conversion_delete_view, name='conversion_delete'),

    # 7. Bill of Materials (BOM)
    path('bom/', views.bom_list_view, name='bom_list'),
    path('bom/new/', views.bom_create_view, name='bom_create'),
    path('bom/<int:pk>/', views.bom_detail_view, name='bom_detail'),
    path('bom/<int:pk>/edit/', views.bom_update_view, name='bom_update'),
    path('bom/<int:pk>/delete/', views.bom_delete_view, name='bom_delete'),
]
