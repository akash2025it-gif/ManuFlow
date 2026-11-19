from decimal import Decimal
from datetime import date
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Sum, Count, Q
from django.utils import timezone

from apps.accounts.decorators import (
    admin_required,
    salesman_required,
    production_required,
    auditor_required,
    owner_required,
)
from apps.accounts.models import CustomUser
from apps.sales.models import SalesOrder, Invoice, Dispatch, PaymentRecord, SalesOrderItem
from apps.sales.services import check_order_stock_availability
from apps.production.models import ProductionRun, ProductionMaterialConsumption
from apps.inventory.models import StockItem, ItemType, GoodsReceiptNote, StockAdjustment
from apps.master_data.models import ProductPackSize, RawMaterial, PackagingMaterial
from apps.core.models import AuditLogEntry


@login_required
def dashboard_dispatcher(request):
    """
    Central dispatcher: evaluates user's role and redirects them
    to their designated role-specific dashboard.
    """
    user = request.user
    if user.is_superuser or user.role == CustomUser.Role.ADMIN:
        return redirect('admin_dashboard')
    elif user.role == CustomUser.Role.SALESMAN:
        return redirect('salesman_dashboard')
    elif user.role == CustomUser.Role.PRODUCTION:
        return redirect('production_dashboard')
    elif user.role == CustomUser.Role.AUDITOR:
        return redirect('auditor_dashboard')
    elif user.role == CustomUser.Role.OWNER:
        return redirect('owner_dashboard')
    elif user.role == CustomUser.Role.ACCOUNTANT:
        return redirect('finance:dashboard')
    return redirect('profile')


@admin_required
def admin_dashboard_view(request):
    """
    System Administration Command Center.
    Provides user management statistics, role breakdown, environment status, and audit overview.
    """
    total_users = CustomUser.objects.count()
    active_users = CustomUser.objects.filter(is_active=True).count()
    role_counts = {
        'admin': CustomUser.objects.filter(role=CustomUser.Role.ADMIN).count(),
        'salesman': CustomUser.objects.filter(role=CustomUser.Role.SALESMAN).count(),
        'production': CustomUser.objects.filter(role=CustomUser.Role.PRODUCTION).count(),
        'auditor': CustomUser.objects.filter(role=CustomUser.Role.AUDITOR).count(),
        'owner': CustomUser.objects.filter(role=CustomUser.Role.OWNER).count(),
        'accountant': CustomUser.objects.filter(role=CustomUser.Role.ACCOUNTANT).count(),
    }
    recent_users = CustomUser.objects.order_by('-date_joined')[:5]
    db_engine = settings.DATABASES['default']['ENGINE'].split('.')[-1]
    recent_audits = AuditLogEntry.objects.select_related('user').order_by('-timestamp')[:5]

    context = {
        'page_title': 'Administrator Command Center',
        'role_title': 'System Administrator',
        'total_users': total_users,
        'active_users': active_users,
        'role_counts': role_counts,
        'recent_users': recent_users,
        'recent_audits': recent_audits,
        'db_engine': db_engine,
        'debug_mode': settings.DEBUG,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


@salesman_required
def salesman_dashboard_view(request):
    """
    Sales Department Portal.
    Pulls live data from database: personal orders, pending approvals, booked pipeline.
    """
    user = request.user
    my_orders = SalesOrder.objects.filter(salesman=user) if not user.is_superuser else SalesOrder.objects.all()

    orders_booked_count = my_orders.count()
    pipeline_agg = my_orders.aggregate(total=Sum('total_amount'))
    pipeline_value = pipeline_agg['total'] or Decimal('0.00')

    pending_quotes = my_orders.filter(status=SalesOrder.Status.DRAFT).count()
    pending_approval_count = my_orders.filter(status=SalesOrder.Status.SUBMITTED).count()
    approved_count = my_orders.filter(status__in=[SalesOrder.Status.APPROVED, SalesOrder.Status.INVOICED, SalesOrder.Status.DISPATCHED]).count()

    recent_orders = my_orders.select_related('customer').order_by('-created_at')[:6]

    context = {
        'page_title': 'Sales Portal & Order Entry',
        'role_title': 'Sales Representative',
        'orders_booked_count': orders_booked_count,
        'pipeline_value': pipeline_value,
        'pending_quotes': pending_quotes,
        'pending_approval_count': pending_approval_count,
        'approved_count': approved_count,
        'recent_orders': recent_orders,
    }
    return render(request, 'dashboard/salesman_dashboard.html', context)


@production_required
def production_dashboard_view(request):
    """
    Production & Manufacturing Floor Dashboard.
    Pulls live data from database: active runs, total finished output, and variance alerts.
    """
    runs = ProductionRun.objects.all()
    completed_runs = runs.filter(status=ProductionRun.Status.COMPLETED)

    total_good_output = completed_runs.aggregate(total=Sum('actual_output_quantity'))['total'] or Decimal('0.00')
    total_planned = completed_runs.aggregate(total=Sum('planned_quantity'))['total'] or Decimal('0.00')
    active_runs_count = runs.filter(status__in=[ProductionRun.Status.DRAFT, ProductionRun.Status.IN_PROGRESS]).count()
    yield_alerts_count = sum(1 for r in runs if r.is_yield_alert_triggered)

    recent_runs = runs.select_related('bill_of_materials', 'bill_of_materials__product', 'product_pack_size').order_by('-created_at')[:6]

    context = {
        'page_title': 'Production Planning & Control Floor',
        'role_title': 'Production Supervisor',
        'total_good_output': total_good_output,
        'total_planned': total_planned,
        'active_runs_count': active_runs_count,
        'completed_runs_count': completed_runs.count(),
        'yield_alerts_count': yield_alerts_count,
        'recent_runs': recent_runs,
    }
    return render(request, 'dashboard/production_dashboard.html', context)


@auditor_required
def auditor_dashboard_view(request):
    """
    Compliance & Internal Audit Observatory.
    Pulls live data from database: system audit log entries, yield alerts, and overdue accounts.
    """
    today = timezone.now().date()
    total_audit_events = AuditLogEntry.objects.count()
    today_audit_events = AuditLogEntry.objects.filter(timestamp__date=today).count()

    recent_audit_entries = AuditLogEntry.objects.select_related('user').order_by('-timestamp')[:8]
    yield_alerts = [r for r in ProductionRun.objects.select_related('product_pack_size', 'product_pack_size__product').order_by('-created_at') if r.is_yield_alert_triggered][:5]
    overdue_invoices = Invoice.objects.filter(
        payment_status__in=[Invoice.PaymentStatus.PENDING, Invoice.PaymentStatus.PARTIAL],
        due_date__lt=today
    ).select_related('customer')[:5]
    recent_dispatches = Dispatch.objects.select_related('sales_order', 'sales_order__customer', 'invoice').order_by('-created_at')[:5]

    context = {
        'page_title': 'Audit & Compliance Observatory',
        'role_title': 'Internal Quality & Financial Auditor',
        'total_audit_events': total_audit_events,
        'today_audit_events': today_audit_events,
        'recent_audit_entries': recent_audit_entries,
        'yield_alerts': yield_alerts,
        'overdue_invoices': overdue_invoices,
        'recent_dispatches': recent_dispatches,
    }
    return render(request, 'dashboard/auditor_dashboard.html', context)


@owner_required
def owner_dashboard_view(request):
    """
    Comprehensive Executive & Business Owner Dashboard.
    Pulls all figures strictly from live database records:
    - Total sales and invoice value
    - Amount collected and outstanding receivables
    - Total production output and yield
    - Current finished goods stock
    - Raw material and packaging stock summary
    - Low-stock alerts
    - Production yield and consumption variance alerts
    - Recent sales orders, invoices, dispatches and payments
    - Monthly sales trend
    - Top-selling products
    - Pending orders requiring approval
    """
    today = timezone.now().date()

    # 1. Total sales and invoice value
    inv_agg = Invoice.objects.aggregate(
        total_invoiced=Sum('grand_total'),
        total_taxable=Sum('taxable_amount'),
        total_tax=Sum('total_tax'),
        total_cgst=Sum('cgst_amount'),
        total_sgst=Sum('sgst_amount'),
        total_igst=Sum('igst_amount'),
        total_collected=Sum('amount_paid'),
        count=Count('id')
    )
    total_invoiced = inv_agg['total_invoiced'] or Decimal('0.00')
    total_taxable = inv_agg['total_taxable'] or Decimal('0.00')
    total_tax = inv_agg['total_tax'] or Decimal('0.00')
    total_cgst = inv_agg['total_cgst'] or Decimal('0.00')
    total_sgst = inv_agg['total_sgst'] or Decimal('0.00')
    total_igst = inv_agg['total_igst'] or Decimal('0.00')
    total_collected = inv_agg['total_collected'] or Decimal('0.00')
    total_outstanding = max(Decimal('0.00'), total_invoiced - total_collected)
    total_invoices_count = inv_agg['count'] or 0

    # Overdue receivables tracking
    overdue_invoices = list(Invoice.objects.filter(
        payment_status__in=[Invoice.PaymentStatus.PENDING, Invoice.PaymentStatus.PARTIAL],
        due_date__lt=today
    ))
    overdue_count = len(overdue_invoices)
    overdue_amount = sum(inv.balance_due for inv in overdue_invoices)

    # Total Sales Orders
    so_agg = SalesOrder.objects.aggregate(total_orders_val=Sum('total_amount'), count=Count('id'))
    total_orders_value = so_agg['total_orders_val'] or Decimal('0.00')
    total_orders_count = so_agg['count'] or 0

    # 2. Total production output
    prod_agg = ProductionRun.objects.filter(status=ProductionRun.Status.COMPLETED).aggregate(
        total_actual_output=Sum('actual_output_quantity'),
        total_planned_output=Sum('planned_quantity'),
        runs_count=Count('id')
    )
    total_production_output = prod_agg['total_actual_output'] or Decimal('0.00')
    total_planned_output = prod_agg['total_planned_output'] or Decimal('0.00')
    completed_runs_count = prod_agg['runs_count'] or 0
    in_progress_runs_count = ProductionRun.objects.filter(
        status__in=[ProductionRun.Status.DRAFT, ProductionRun.Status.IN_PROGRESS]
    ).count()

    overall_yield_pct = Decimal('0.00')
    if total_planned_output > Decimal('0.00'):
        overall_yield_pct = ((total_production_output / total_planned_output) * Decimal('100.00')).quantize(Decimal('0.01'))

    # 3. Current finished goods stock
    fg_stock_items = StockItem.objects.filter(
        item_type=ItemType.FINISHED_GOODS,
        quantity_on_hand__gt=0
    ).select_related('product_pack_size', 'product_pack_size__product', 'uom')
    total_fg_packets = sum(s.quantity_on_hand for s in fg_stock_items)
    total_fg_valuation = sum(s.quantity_on_hand * s.unit_cost for s in fg_stock_items)

    # 4. Raw material and packaging stock summary
    raw_stock_items = StockItem.objects.filter(
        item_type=ItemType.RAW_MATERIAL,
        quantity_on_hand__gt=0
    ).select_related('raw_material', 'uom').order_by('raw_material__name')
    total_raw_valuation = sum(s.quantity_on_hand * s.unit_cost for s in raw_stock_items)

    pkg_stock_items = StockItem.objects.filter(
        item_type=ItemType.PACKAGING_MATERIAL,
        quantity_on_hand__gt=0
    ).select_related('packaging_material', 'uom').order_by('packaging_material__name')
    total_pkg_valuation = sum(s.quantity_on_hand * s.unit_cost for s in pkg_stock_items)

    total_inventory_valuation = total_fg_valuation + total_raw_valuation + total_pkg_valuation

    # Aggregate by Raw Material SKU
    raw_materials_summary = []
    for rm in RawMaterial.objects.filter(is_active=True).select_related('uom'):
        rm_stocks = [s for s in raw_stock_items if s.raw_material_id == rm.id]
        qty = sum(s.quantity_on_hand for s in rm_stocks)
        val = sum(s.quantity_on_hand * s.unit_cost for s in rm_stocks)
        raw_materials_summary.append({
            'code': rm.code,
            'name': rm.name,
            'quantity': qty,
            'uom': rm.uom.code if rm.uom else '',
            'reorder_level': rm.reorder_level,
            'is_low_stock': qty <= rm.reorder_level if rm.reorder_level > 0 else False,
            'valuation': val,
        })

    # Aggregate by Packaging Material SKU
    pkg_materials_summary = []
    for pm in PackagingMaterial.objects.filter(is_active=True).select_related('uom'):
        pm_stocks = [s for s in pkg_stock_items if s.packaging_material_id == pm.id]
        qty = sum(s.quantity_on_hand for s in pm_stocks)
        val = sum(s.quantity_on_hand * s.unit_cost for s in pm_stocks)
        pkg_materials_summary.append({
            'code': pm.code,
            'name': pm.name,
            'quantity': qty,
            'uom': pm.uom.code if pm.uom else '',
            'reorder_level': pm.reorder_level,
            'is_low_stock': qty <= pm.reorder_level if pm.reorder_level > 0 else False,
            'valuation': val,
        })

    # 5. Low-stock alerts
    low_stock_alerts = [m for m in raw_materials_summary if m['is_low_stock']] + \
                       [m for m in pkg_materials_summary if m['is_low_stock']]

    # 6. Production yield and consumption variance alerts
    yield_alert_runs = [
        r for r in ProductionRun.objects.select_related('product_pack_size', 'product_pack_size__product').order_by('-created_at')
        if r.is_yield_alert_triggered
    ][:5]

    consumption_alert_items = [
        i for i in ProductionMaterialConsumption.objects.select_related(
            'production_run', 'raw_material', 'packaging_material', 'uom'
        ).order_by('-id')
        if i.is_variance_alert_triggered
    ][:6]

    # 7. Recent transactions: orders, invoices, dispatches, payments
    recent_orders = SalesOrder.objects.select_related('customer', 'salesman').order_by('-created_at')[:5]
    recent_invoices = Invoice.objects.select_related('customer', 'sales_order').order_by('-created_at')[:5]
    recent_dispatches = Dispatch.objects.select_related('sales_order', 'sales_order__customer', 'invoice').order_by('-created_at')[:5]
    recent_payments = PaymentRecord.objects.select_related('invoice', 'customer').order_by('-created_at')[:5]

    # 8. Monthly sales trend (current calendar year)
    current_year = today.year
    monthly_trend = []
    year_invoices = list(Invoice.objects.filter(invoice_date__year=current_year))
    for m in range(1, 13):
        m_invs = [inv for inv in year_invoices if inv.invoice_date.month == m]
        if m_invs:
            m_taxable = sum(i.taxable_amount for i in m_invs)
            m_total = sum(i.grand_total for i in m_invs)
            m_collected = sum(i.amount_paid for i in m_invs)
            monthly_trend.append({
                'month_name': date(current_year, m, 1).strftime('%B'),
                'month_abbr': date(current_year, m, 1).strftime('%b'),
                'month_num': m,
                'taxable': m_taxable,
                'total': m_total,
                'collected': m_collected,
                'count': len(m_invs)
            })

    # 9. Top-selling products
    top_products = list(
        SalesOrderItem.objects.values(
            'product_pack_size__sku_code',
            'product_pack_size__pack_name',
            'product_pack_size__product__name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price')
        ).order_by('-total_quantity')[:5]
    )

    # 10. Pending orders requiring approval with stock sufficiency check
    pending_orders_raw = SalesOrder.objects.filter(
        status=SalesOrder.Status.SUBMITTED
    ).select_related('customer', 'salesman').order_by('-created_at')

    pending_orders = []
    for order in pending_orders_raw:
        can_fulfill, item, on_hand, req = check_order_stock_availability(order)
        shortage = (req - on_hand) if (not can_fulfill and req > on_hand) else Decimal('0.00')
        pending_orders.append({
            'order': order,
            'can_fulfill': can_fulfill,
            'shortage': shortage,
            'available_on_hand': on_hand,
            'required_qty': req,
        })

    context = {
        'page_title': 'Executive Leadership Suite',
        'role_title': 'Managing Director & Enterprise Owner',

        # 1. Total Sales & Receivables
        'total_invoiced': total_invoiced,
        'total_taxable': total_taxable,
        'total_tax': total_tax,
        'total_cgst': total_cgst,
        'total_sgst': total_sgst,
        'total_igst': total_igst,
        'total_collected': total_collected,
        'total_outstanding': total_outstanding,
        'total_invoices_count': total_invoices_count,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'total_orders_value': total_orders_value,
        'total_orders_count': total_orders_count,

        # 2. Production Output & Yield
        'total_production_output': total_production_output,
        'total_planned_output': total_planned_output,
        'completed_runs_count': completed_runs_count,
        'in_progress_runs_count': in_progress_runs_count,
        'overall_yield_pct': overall_yield_pct,

        # 3. Finished Goods Stock
        'total_fg_packets': total_fg_packets,
        'total_fg_valuation': total_fg_valuation,
        'fg_stock_items': fg_stock_items,

        # 4. Raw Material & Packaging Summary
        'raw_materials_summary': raw_materials_summary,
        'pkg_materials_summary': pkg_materials_summary,
        'total_raw_valuation': total_raw_valuation,
        'total_pkg_valuation': total_pkg_valuation,
        'total_inventory_valuation': total_inventory_valuation,

        # 5. Low-stock alerts
        'low_stock_alerts': low_stock_alerts,

        # 6. Variance Alerts
        'yield_alert_runs': yield_alert_runs,
        'consumption_alert_items': consumption_alert_items,

        # 7. Recent Transactions
        'recent_orders': recent_orders,
        'recent_invoices': recent_invoices,
        'recent_dispatches': recent_dispatches,
        'recent_payments': recent_payments,

        # 8. Monthly Trend & Top Products
        'monthly_trend': monthly_trend,
        'top_products': top_products,

        # 9. Pending Orders
        'pending_orders': pending_orders,
    }
    return render(request, 'dashboard/owner_dashboard.html', context)
