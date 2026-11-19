from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.db import transaction

from .models import (
    UnitOfMeasurement,
    UnitConversion,
    Supplier,
    Customer,
    RawMaterial,
    PackagingMaterial,
    Product,
    ProductPackSize,
    BillOfMaterials,
    BOMItem,
)
from .forms import (
    UnitOfMeasurementForm,
    UnitConversionForm,
    SupplierForm,
    CustomerForm,
    RawMaterialForm,
    PackagingMaterialForm,
    ProductForm,
    ProductPackSizeForm,
    BillOfMaterialsForm,
    BOMItemFormSet,
)
from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event
from .permissions import (
    can_view_master_data,
    can_manage_products,
    can_manage_bom,
    can_manage_materials,
    can_manage_customers,
    can_manage_suppliers,
    can_manage_uom,
)


# ==============================================================================
# Master Data Central Hub
# ==============================================================================

@can_view_master_data
def master_data_hub_view(request):
    """
    Central hub presenting metrics, stats, and shortcuts to all 7 master data modules.
    """
    context = {
        'page_title': 'Master Data Hub | NIT O2A Management',
        'counts': {
            'products': Product.objects.count(),
            'pack_sizes': ProductPackSize.objects.count(),
            'customers': Customer.objects.count(),
            'suppliers': Supplier.objects.count(),
            'raw_materials': RawMaterial.objects.count(),
            'packaging_materials': PackagingMaterial.objects.count(),
            'uoms': UnitOfMeasurement.objects.count(),
            'boms': BillOfMaterials.objects.count(),
        },
        'recent_products': Product.objects.select_related('base_uom').order_by('-created_at')[:5],
        'recent_boms': BillOfMaterials.objects.select_related('product', 'output_uom').order_by('-created_at')[:5],
    }
    return render(request, 'master_data/hub.html', context)


# ==============================================================================
# 1. Products and Pack Sizes
# ==============================================================================

@can_view_master_data
def product_list_view(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    status = request.GET.get('status', '').strip()

    products = Product.objects.select_related('base_uom').prefetch_related('pack_sizes', 'boms')

    if query:
        products = products.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(description__icontains=query))
    if category:
        products = products.filter(category__iexact=category)
    if status == 'active':
        products = products.filter(is_active=True)
    elif status == 'inactive':
        products = products.filter(is_active=False)

    categories = Product.objects.values_list('category', flat=True).distinct()

    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'master_data/product_list.html', {
        'page_title': 'Finished Products Master Catalog',
        'page_obj': page_obj,
        'query': query,
        'category': category,
        'status': status,
        'categories': categories,
    })


@can_view_master_data
def product_detail_view(request, pk):
    product = get_object_or_404(Product.objects.select_related('base_uom'), pk=pk)
    pack_sizes = product.pack_sizes.select_related('uom', 'primary_packaging').all()
    boms = product.boms.select_related('output_uom').prefetch_related('items').all()

    return render(request, 'master_data/product_detail.html', {
        'page_title': f"{product.name} ({product.code})",
        'product': product,
        'pack_sizes': pack_sizes,
        'boms': boms,
    })


@can_manage_products
def product_create_view(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()
            log_audit_event(
                action=AuditLogEntry.Action.MASTER_DATA_CREATE,
                module=AuditLogEntry.Module.MASTER_DATA,
                object_repr=f"Product {product.code} - {product.name}",
                object_id=str(product.pk),
                user=request.user,
                request=request,
                details={'code': product.code, 'name': product.name}
            )
            messages.success(request, f"Finished Product '{product.name}' ({product.code}) was successfully created.")
            return redirect('product_detail', pk=product.pk)
    else:
        form = ProductForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Create Finished Product',
        'form_title': 'New Finished Product Definition',
        'form': form,
        'back_url': 'product_list',
    })


@can_manage_products
def product_update_view(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            log_audit_event(
                action=AuditLogEntry.Action.MASTER_DATA_UPDATE,
                module=AuditLogEntry.Module.MASTER_DATA,
                object_repr=f"Product {product.code} - {product.name}",
                object_id=str(product.pk),
                user=request.user,
                request=request,
                details={'code': product.code, 'name': product.name}
            )
            messages.success(request, f"Product '{product.name}' details updated successfully.")
            return redirect('product_detail', pk=product.pk)
    else:
        form = ProductForm(instance=product)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit Product: {product.name}",
        'form_title': f"Edit Product [{product.code}]",
        'form': form,
        'back_url': 'product_detail',
        'back_pk': product.pk,
    })


@can_manage_products
def product_delete_view(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        name = product.name
        code = product.code
        product.delete()
        messages.success(request, f"Product '{name}' ({code}) has been removed.")
        return redirect('product_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Confirm Deletion: {product.name}",
        'object_name': f"Finished Product: {product.name} ({product.code})",
        'back_url': 'product_detail',
        'back_pk': product.pk,
    })


@can_manage_products
def pack_size_create_view(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    if request.method == 'POST':
        form = ProductPackSizeForm(request.POST)
        if form.is_valid():
            pack_size = form.save(commit=False)
            pack_size.product = product
            pack_size.save()
            messages.success(request, f"Pack SKU '{pack_size.sku_code}' added to {product.name}.")
            return redirect('product_detail', pk=product.pk)
    else:
        form = ProductPackSizeForm(initial={'product': product, 'uom': product.base_uom})

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Add Pack SKU for {product.name}",
        'form_title': f"New Pack Size / SKU for {product.name}",
        'form': form,
        'back_url': 'product_detail',
        'back_pk': product.pk,
    })


@can_manage_products
def pack_size_update_view(request, pk):
    pack_size = get_object_or_404(ProductPackSize.objects.select_related('product'), pk=pk)
    if request.method == 'POST':
        form = ProductPackSizeForm(request.POST, instance=pack_size)
        if form.is_valid():
            form.save()
            messages.success(request, f"Pack SKU '{pack_size.sku_code}' updated successfully.")
            return redirect('product_detail', pk=pack_size.product.pk)
    else:
        form = ProductPackSizeForm(instance=pack_size)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit Pack SKU: {pack_size.sku_code}",
        'form_title': f"Edit Pack SKU: {pack_size.sku_code}",
        'form': form,
        'back_url': 'product_detail',
        'back_pk': pack_size.product.pk,
    })


@can_manage_products
def pack_size_delete_view(request, pk):
    pack_size = get_object_or_404(ProductPackSize.objects.select_related('product'), pk=pk)
    product_pk = pack_size.product.pk
    if request.method == 'POST':
        sku = pack_size.sku_code
        pack_size.delete()
        messages.success(request, f"Pack SKU '{sku}' removed.")
        return redirect('product_detail', pk=product_pk)

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete Pack SKU: {pack_size.sku_code}",
        'object_name': f"Pack SKU: {pack_size.sku_code} ({pack_size.pack_name})",
        'back_url': 'product_detail',
        'back_pk': product_pk,
    })


# ==============================================================================
# 2. Customers (Retailers and Distributors)
# ==============================================================================

@can_view_master_data
def customer_list_view(request):
    query = request.GET.get('q', '').strip()
    customer_type = request.GET.get('type', '').strip()
    status = request.GET.get('status', '').strip()

    customers = Customer.objects.all()

    if query:
        customers = customers.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(tax_id_gst__icontains=query) |
            Q(city__icontains=query)
        )
    if customer_type:
        customers = customers.filter(customer_type=customer_type)
    if status == 'active':
        customers = customers.filter(is_active=True)
    elif status == 'inactive':
        customers = customers.filter(is_active=False)

    paginator = Paginator(customers, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'master_data/customer_list.html', {
        'page_title': 'Customer Master Directory',
        'page_obj': page_obj,
        'query': query,
        'customer_type': customer_type,
        'status': status,
    })


@can_view_master_data
def customer_detail_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    return render(request, 'master_data/customer_detail.html', {
        'page_title': f"Customer: {customer.name}",
        'customer': customer,
    })


@can_manage_customers
def customer_create_view(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            log_audit_event(
                action=AuditLogEntry.Action.MASTER_DATA_CREATE,
                module=AuditLogEntry.Module.MASTER_DATA,
                object_repr=f"Customer {customer.code} - {customer.name}",
                object_id=str(customer.pk),
                user=request.user,
                request=request,
                details={'code': customer.code, 'name': customer.name, 'state': customer.state}
            )
            messages.success(request, f"Customer '{customer.name}' ({customer.code}) created successfully.")
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Onboard New Customer',
        'form_title': 'Customer Registration (Retailer / Distributor)',
        'form': form,
        'back_url': 'customer_list',
    })


@can_manage_customers
def customer_update_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            log_audit_event(
                action=AuditLogEntry.Action.MASTER_DATA_UPDATE,
                module=AuditLogEntry.Module.MASTER_DATA,
                object_repr=f"Customer {customer.code} - {customer.name}",
                object_id=str(customer.pk),
                user=request.user,
                request=request,
                details={'code': customer.code, 'name': customer.name, 'state': customer.state}
            )
            messages.success(request, f"Customer '{customer.name}' updated successfully.")
            return redirect('customer_detail', pk=customer.pk)
    else:
        form = CustomerForm(instance=customer)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit Customer: {customer.name}",
        'form_title': f"Edit Customer Profile [{customer.code}]",
        'form': form,
        'back_url': 'customer_detail',
        'back_pk': customer.pk,
    })


@can_manage_customers
def customer_delete_view(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if request.method == 'POST':
        name = customer.name
        customer.delete()
        messages.success(request, f"Customer '{name}' was deleted.")
        return redirect('customer_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete Customer: {customer.name}",
        'object_name': f"Customer: {customer.name} ({customer.code})",
        'back_url': 'customer_detail',
        'back_pk': customer.pk,
    })


# ==============================================================================
# 3. Suppliers
# ==============================================================================

@can_view_master_data
def supplier_list_view(request):
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    suppliers = Supplier.objects.all()

    if query:
        suppliers = suppliers.filter(
            Q(code__icontains=query) |
            Q(name__icontains=query) |
            Q(contact_person__icontains=query) |
            Q(tax_id_gst__icontains=query) |
            Q(city__icontains=query)
        )
    if status == 'active':
        suppliers = suppliers.filter(is_active=True)
    elif status == 'inactive':
        suppliers = suppliers.filter(is_active=False)

    paginator = Paginator(suppliers, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'master_data/supplier_list.html', {
        'page_title': 'Supplier Master Directory',
        'page_obj': page_obj,
        'query': query,
        'status': status,
    })


@can_view_master_data
def supplier_detail_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    raw_materials = supplier.raw_materials.select_related('uom').all()
    packaging_materials = supplier.packaging_materials.select_related('uom').all()

    return render(request, 'master_data/supplier_detail.html', {
        'page_title': f"Supplier: {supplier.name}",
        'supplier': supplier,
        'raw_materials': raw_materials,
        'packaging_materials': packaging_materials,
    })


@can_manage_suppliers
def supplier_create_view(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f"Supplier '{supplier.name}' ({supplier.code}) added successfully.")
            return redirect('supplier_detail', pk=supplier.pk)
    else:
        form = SupplierForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Add Supplier Record',
        'form_title': 'New Approved Vendor Registration',
        'form': form,
        'back_url': 'supplier_list',
    })


@can_manage_suppliers
def supplier_update_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f"Supplier '{supplier.name}' updated successfully.")
            return redirect('supplier_detail', pk=supplier.pk)
    else:
        form = SupplierForm(instance=supplier)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit Supplier: {supplier.name}",
        'form_title': f"Edit Supplier [{supplier.code}]",
        'form': form,
        'back_url': 'supplier_detail',
        'back_pk': supplier.pk,
    })


@can_manage_suppliers
def supplier_delete_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        name = supplier.name
        supplier.delete()
        messages.success(request, f"Supplier '{name}' was deleted.")
        return redirect('supplier_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete Supplier: {supplier.name}",
        'object_name': f"Supplier: {supplier.name} ({supplier.code})",
        'back_url': 'supplier_detail',
        'back_pk': supplier.pk,
    })


# ==============================================================================
# 4. Raw Materials
# ==============================================================================

@can_view_master_data
def raw_material_list_view(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    status = request.GET.get('status', '').strip()

    materials = RawMaterial.objects.select_related('uom', 'preferred_supplier')

    if query:
        materials = materials.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(category__icontains=query))
    if category:
        materials = materials.filter(category__iexact=category)
    if status == 'active':
        materials = materials.filter(is_active=True)
    elif status == 'inactive':
        materials = materials.filter(is_active=False)

    categories = RawMaterial.objects.values_list('category', flat=True).distinct()
    paginator = Paginator(materials, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'master_data/raw_material_list.html', {
        'page_title': 'Raw Materials Master Catalog',
        'page_obj': page_obj,
        'query': query,
        'category': category,
        'status': status,
        'categories': categories,
    })


@can_view_master_data
def raw_material_detail_view(request, pk):
    material = get_object_or_404(RawMaterial.objects.select_related('uom', 'preferred_supplier'), pk=pk)
    bom_usages = material.bom_items.select_related('bom', 'bom__product', 'uom').all()

    return render(request, 'master_data/raw_material_detail.html', {
        'page_title': f"Raw Material: {material.name}",
        'material': material,
        'bom_usages': bom_usages,
    })


@can_manage_materials
def raw_material_create_view(request):
    if request.method == 'POST':
        form = RawMaterialForm(request.POST)
        if form.is_valid():
            material = form.save()
            messages.success(request, f"Raw Material '{material.name}' ({material.code}) created successfully.")
            return redirect('raw_material_detail', pk=material.pk)
    else:
        form = RawMaterialForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Add Raw Material',
        'form_title': 'New Raw Material Definition',
        'form': form,
        'back_url': 'raw_material_list',
    })


@can_manage_materials
def raw_material_update_view(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    if request.method == 'POST':
        form = RawMaterialForm(request.POST, instance=material)
        if form.is_valid():
            form.save()
            messages.success(request, f"Raw Material '{material.name}' updated successfully.")
            return redirect('raw_material_detail', pk=material.pk)
    else:
        form = RawMaterialForm(instance=material)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit Raw Material: {material.name}",
        'form_title': f"Edit Raw Material [{material.code}]",
        'form': form,
        'back_url': 'raw_material_detail',
        'back_pk': material.pk,
    })


@can_manage_materials
def raw_material_delete_view(request, pk):
    material = get_object_or_404(RawMaterial, pk=pk)
    if request.method == 'POST':
        name = material.name
        material.delete()
        messages.success(request, f"Raw Material '{name}' was removed.")
        return redirect('raw_material_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete Raw Material: {material.name}",
        'object_name': f"Raw Material: {material.name} ({material.code})",
        'back_url': 'raw_material_detail',
        'back_pk': material.pk,
    })


# ==============================================================================
# 5. Packaging Materials
# ==============================================================================

@can_view_master_data
def packaging_material_list_view(request):
    query = request.GET.get('q', '').strip()
    material_type = request.GET.get('type', '').strip()
    status = request.GET.get('status', '').strip()

    materials = PackagingMaterial.objects.select_related('uom', 'preferred_supplier')

    if query:
        materials = materials.filter(Q(code__icontains=query) | Q(name__icontains=query))
    if material_type:
        materials = materials.filter(material_type=material_type)
    if status == 'active':
        materials = materials.filter(is_active=True)
    elif status == 'inactive':
        materials = materials.filter(is_active=False)

    paginator = Paginator(materials, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'master_data/packaging_material_list.html', {
        'page_title': 'Packaging Materials Master Catalog',
        'page_obj': page_obj,
        'query': query,
        'material_type': material_type,
        'status': status,
        'type_choices': PackagingMaterial.MaterialType.choices,
    })


@can_view_master_data
def packaging_material_detail_view(request, pk):
    material = get_object_or_404(PackagingMaterial.objects.select_related('uom', 'preferred_supplier'), pk=pk)
    pack_usages = material.pack_sizes.select_related('product', 'uom').all()
    bom_usages = material.bom_items.select_related('bom', 'bom__product', 'uom').all()

    return render(request, 'master_data/packaging_material_detail.html', {
        'page_title': f"Packaging Material: {material.name}",
        'material': material,
        'pack_usages': pack_usages,
        'bom_usages': bom_usages,
    })


@can_manage_materials
def packaging_material_create_view(request):
    if request.method == 'POST':
        form = PackagingMaterialForm(request.POST)
        if form.is_valid():
            material = form.save()
            messages.success(request, f"Packaging Material '{material.name}' ({material.code}) created successfully.")
            return redirect('packaging_material_detail', pk=material.pk)
    else:
        form = PackagingMaterialForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Add Packaging Material',
        'form_title': 'New Packaging Component Definition',
        'form': form,
        'back_url': 'packaging_material_list',
    })


@can_manage_materials
def packaging_material_update_view(request, pk):
    material = get_object_or_404(PackagingMaterial, pk=pk)
    if request.method == 'POST':
        form = PackagingMaterialForm(request.POST, instance=material)
        if form.is_valid():
            form.save()
            messages.success(request, f"Packaging Material '{material.name}' updated successfully.")
            return redirect('packaging_material_detail', pk=material.pk)
    else:
        form = PackagingMaterialForm(instance=material)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit Packaging Material: {material.name}",
        'form_title': f"Edit Packaging Component [{material.code}]",
        'form': form,
        'back_url': 'packaging_material_detail',
        'back_pk': material.pk,
    })


@can_manage_materials
def packaging_material_delete_view(request, pk):
    material = get_object_or_404(PackagingMaterial, pk=pk)
    if request.method == 'POST':
        name = material.name
        material.delete()
        messages.success(request, f"Packaging Material '{name}' was removed.")
        return redirect('packaging_material_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete Packaging Material: {material.name}",
        'object_name': f"Packaging Material: {material.name} ({material.code})",
        'back_url': 'packaging_material_detail',
        'back_pk': material.pk,
    })


# ==============================================================================
# 6. Units of Measurement and Conversions
# ==============================================================================

@can_view_master_data
def uom_list_view(request):
    uoms = UnitOfMeasurement.objects.all().order_by('uom_type', 'code')
    conversions = UnitConversion.objects.select_related('from_uom', 'to_uom').all()

    return render(request, 'master_data/uom_list.html', {
        'page_title': 'Units of Measurement & Conversions',
        'uoms': uoms,
        'conversions': conversions,
    })


@can_manage_uom
def uom_create_view(request):
    if request.method == 'POST':
        form = UnitOfMeasurementForm(request.POST)
        if form.is_valid():
            uom = form.save()
            messages.success(request, f"Unit of Measurement '{uom.code}' ({uom.name}) added.")
            return redirect('uom_list')
    else:
        form = UnitOfMeasurementForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Create Unit of Measurement',
        'form_title': 'New Unit of Measurement Definition',
        'form': form,
        'back_url': 'uom_list',
    })


@can_manage_uom
def uom_update_view(request, pk):
    uom = get_object_or_404(UnitOfMeasurement, pk=pk)
    if request.method == 'POST':
        form = UnitOfMeasurementForm(request.POST, instance=uom)
        if form.is_valid():
            form.save()
            messages.success(request, f"Unit '{uom.code}' updated successfully.")
            return redirect('uom_list')
    else:
        form = UnitOfMeasurementForm(instance=uom)

    return render(request, 'master_data/form_generic.html', {
        'page_title': f"Edit UOM: {uom.code}",
        'form_title': f"Edit Unit of Measurement [{uom.code}]",
        'form': form,
        'back_url': 'uom_list',
    })


@can_manage_uom
def uom_delete_view(request, pk):
    uom = get_object_or_404(UnitOfMeasurement, pk=pk)
    if request.method == 'POST':
        code = uom.code
        uom.delete()
        messages.success(request, f"Unit '{code}' deleted.")
        return redirect('uom_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete UOM: {uom.code}",
        'object_name': f"Unit of Measurement: {uom.code} ({uom.name})",
        'back_url': 'uom_list',
    })


@can_manage_uom
def conversion_create_view(request):
    if request.method == 'POST':
        form = UnitConversionForm(request.POST)
        if form.is_valid():
            conversion = form.save()
            messages.success(request, f"Unit conversion rule added: 1 {conversion.from_uom.code} = {conversion.multiplier} {conversion.to_uom.code}.")
            return redirect('uom_list')
    else:
        form = UnitConversionForm()

    return render(request, 'master_data/form_generic.html', {
        'page_title': 'Define Unit Conversion',
        'form_title': 'New Unit Conversion Factor',
        'form': form,
        'back_url': 'uom_list',
    })


@can_manage_uom
def conversion_delete_view(request, pk):
    conversion = get_object_or_404(UnitConversion, pk=pk)
    if request.method == 'POST':
        conversion.delete()
        messages.success(request, "Conversion rule removed.")
        return redirect('uom_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': 'Delete Unit Conversion',
        'object_name': f"Conversion rule: {conversion}",
        'back_url': 'uom_list',
    })


# ==============================================================================
# 7. Bill of Materials (BOM)
# ==============================================================================

@can_view_master_data
def bom_list_view(request):
    query = request.GET.get('q', '').strip()
    product_id = request.GET.get('product', '').strip()
    status = request.GET.get('status', '').strip()

    boms = BillOfMaterials.objects.select_related('product', 'output_uom').prefetch_related('items')

    if query:
        boms = boms.filter(Q(bom_code__icontains=query) | Q(name__icontains=query) | Q(product__name__icontains=query))
    if product_id:
        boms = boms.filter(product_id=product_id)
    if status == 'active':
        boms = boms.filter(is_active_version=True)
    elif status == 'inactive':
        boms = boms.filter(is_active_version=False)

    products = Product.objects.all().order_by('name')
    paginator = Paginator(boms, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'master_data/bom_list.html', {
        'page_title': 'Bill of Materials (BOM) Specifications',
        'page_obj': page_obj,
        'query': query,
        'product_id': product_id,
        'status': status,
        'products': products,
    })


@can_view_master_data
def bom_detail_view(request, pk):
    bom = get_object_or_404(
        BillOfMaterials.objects.select_related('product', 'output_uom'),
        pk=pk
    )
    items = bom.items.select_related('raw_material', 'packaging_material', 'uom').all()

    return render(request, 'master_data/bom_detail.html', {
        'page_title': f"BOM: {bom.bom_code} - {bom.product.name}",
        'bom': bom,
        'items': items,
    })


@can_manage_bom
def bom_create_view(request):
    """
    Creates a new Bill of Materials including multiple ingredient lines.
    """
    if request.method == 'POST':
        form = BillOfMaterialsForm(request.POST)
        formset = BOMItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                bom = form.save()
                formset.instance = bom
                formset.save()

            log_audit_event(
                action=AuditLogEntry.Action.MASTER_DATA_CREATE,
                module=AuditLogEntry.Module.MASTER_DATA,
                object_repr=f"BOM {bom.bom_code} for {bom.product.name}",
                object_id=str(bom.pk),
                user=request.user,
                request=request,
                details={'bom_code': bom.bom_code, 'product': bom.product.name, 'batch_size': bom.batch_size}
            )
            messages.success(request, f"Bill of Materials '{bom.bom_code}' for {bom.product.name} created successfully.")
            return redirect('bom_detail', pk=bom.pk)
    else:
        initial_product = request.GET.get('product')
        form = BillOfMaterialsForm(initial={'product': initial_product} if initial_product else None)
        formset = BOMItemFormSet()

    return render(request, 'master_data/bom_form.html', {
        'page_title': 'Create Bill of Materials (BOM)',
        'form': form,
        'formset': formset,
        'back_url': 'bom_list',
    })


@can_manage_bom
def bom_update_view(request, pk):
    """
    Updates an existing Bill of Materials and its component ingredients.
    """
    bom = get_object_or_404(BillOfMaterials, pk=pk)
    if request.method == 'POST':
        form = BillOfMaterialsForm(request.POST, instance=bom)
        formset = BOMItemFormSet(request.POST, instance=bom)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, f"BOM '{bom.bom_code}' updated successfully.")
            return redirect('bom_detail', pk=bom.pk)
    else:
        form = BillOfMaterialsForm(instance=bom)
        formset = BOMItemFormSet(instance=bom)

    return render(request, 'master_data/bom_form.html', {
        'page_title': f"Edit BOM: {bom.bom_code}",
        'form': form,
        'formset': formset,
        'bom': bom,
        'back_url': 'bom_detail',
        'back_pk': bom.pk,
    })


@can_manage_bom
def bom_delete_view(request, pk):
    bom = get_object_or_404(BillOfMaterials, pk=pk)
    if request.method == 'POST':
        code = bom.bom_code
        bom.delete()
        messages.success(request, f"Bill of Materials '{code}' was removed.")
        return redirect('bom_list')

    return render(request, 'master_data/confirm_delete.html', {
        'page_title': f"Delete BOM: {bom.bom_code}",
        'object_name': f"Bill of Materials: {bom.bom_code} for {bom.product.name}",
        'back_url': 'bom_detail',
        'back_pk': bom.pk,
    })
