from decimal import Decimal
from datetime import date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import HttpResponse, Http404

from apps.accounts.decorators import role_required, accountant_required, auditor_required
from apps.sales.models import Invoice, PaymentRecord, SalesOrder, Dispatch
from apps.sales.services import record_invoice_payment
from .forms import (
    FinancePaymentForm,
    SalesRegisterFilterForm,
    MonthlyGSTFilterForm,
    StockFilterForm,
    StockLedgerFilterForm,
    DateRangeFilterForm,
)
from .services import (
    get_receivables_summary,
    get_customer_receivables_summary,
    get_overdue_invoices,
    get_sales_register,
    get_monthly_gst_summary,
    get_current_stock_report,
    get_stock_movement_report,
    get_production_variance_report,
    get_sales_dispatch_report,
    export_to_csv,
    export_to_excel_xml,
)


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


# ======================================================================
# 1. FINANCE & REPORTING DASHBOARD
# ======================================================================

@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'OWNER'])
def finance_dashboard_view(request):
    """
    Financial & Accounts Control Dashboard.
    Provides real-time receivables, monthly GST summary, and quick access to audits.
    """
    receivables_kpis = get_receivables_summary()
    current_year = date.today().year
    monthly_gst, year_totals = get_monthly_gst_summary(current_year)
    recent_payments = PaymentRecord.objects.select_related('invoice', 'customer', 'recorded_by').order_by('-created_at')[:5]
    overdue_invoices = get_overdue_invoices()[:5]

    context = {
        'kpis': receivables_kpis,
        'current_year': current_year,
        'year_totals': year_totals,
        'monthly_gst': monthly_gst,
        'recent_payments': recent_payments,
        'overdue_invoices': overdue_invoices,
    }
    return render(request, 'finance/dashboard.html', context)


# ======================================================================
# 2. RECEIVABLES MANAGEMENT
# ======================================================================

@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'OWNER'])
def receivables_summary_view(request):
    """
    Comprehensive Receivables Management:
    - Overall receivables KPIs
    - Customer-wise outstanding balances, credit terms, and overdue tracking
    - Overdue invoice alert table
    """
    receivables_kpis = get_receivables_summary()
    customer_summaries = get_customer_receivables_summary()
    overdue_invoices = get_overdue_invoices()

    context = {
        'kpis': receivables_kpis,
        'customer_summaries': customer_summaries,
        'overdue_invoices': overdue_invoices,
        'today': date.today(),
    }
    return render(request, 'finance/receivables_summary.html', context)


# ======================================================================
# 3. PAYMENT MANAGEMENT (RECORDING & AUDIT TRAIL)
# ======================================================================

@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'OWNER'])
def payments_list_view(request):
    """
    Audit ledger of all recorded customer payment vouchers.
    Read-only for Auditor; full view for Accountant, Admin, and Owner.
    """
    payments = PaymentRecord.objects.select_related(
        'invoice', 'customer', 'recorded_by'
    ).order_by('-payment_date', '-created_at')

    total_amount = sum(p.amount for p in payments)

    context = {
        'payments': payments,
        'total_amount': total_amount,
        'total_count': len(payments),
    }
    return render(request, 'finance/payment_list.html', context)


@login_required
@accountant_required
def payment_create_view(request):
    """
    Record customer payment against an invoice.
    Restricted to Accountant, Admin, and Owner (Auditor cannot record payments).
    Prevents overpayment and payments on already paid invoices.
    """
    invoice_id = request.GET.get('invoice') or request.POST.get('invoice')
    selected_invoice = None
    if invoice_id:
        try:
            selected_invoice = Invoice.objects.select_related('customer').get(pk=invoice_id)
        except (Invoice.DoesNotExist, ValueError):
            pass

    if request.method == 'POST':
        form = FinancePaymentForm(request.POST, invoice_id=invoice_id)
        if form.is_valid():
            inv = form.cleaned_data['invoice']
            amt = form.cleaned_data['amount']
            mode = form.cleaned_data['payment_mode']
            ref = form.cleaned_data['transaction_reference']
            notes = form.cleaned_data['notes']
            p_date = form.cleaned_data['payment_date']

            try:
                payment = record_invoice_payment(
                    invoice=inv,
                    amount=amt,
                    payment_mode=mode,
                    transaction_reference=ref,
                    recorded_by=request.user,
                    notes=notes
                )
                if p_date and p_date != payment.payment_date:
                    payment.payment_date = p_date
                    payment.save(update_fields=['payment_date'])

                messages.success(
                    request,
                    f"Payment voucher {payment.payment_number} of ₹{amt:,.2f} recorded successfully for Invoice {inv.invoice_number} ({inv.customer.name})."
                )
                return redirect('finance:payments_list')
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
    else:
        initial = {}
        if selected_invoice:
            initial['invoice'] = selected_invoice.id
            initial['amount'] = selected_invoice.balance_due
        form = FinancePaymentForm(initial=initial, invoice_id=invoice_id)

    context = {
        'form': form,
        'selected_invoice': selected_invoice,
    }
    return render(request, 'finance/payment_create.html', context)


# ======================================================================
# 4. GST REPORTS
# ======================================================================

@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'SALESMAN', 'OWNER'])
def gst_sales_register_view(request):
    """
    GST Sales Register with clear distinction between:
    - Intra-State (Tamil Nadu: 2.5% CGST + 2.5% SGST)
    - Inter-State (Outside Tamil Nadu: 5% IGST)
    Includes date-range and state filtering.
    Prominently displays Academic / Demo simulation disclaimer.
    """
    form = SalesRegisterFilterForm(request.GET)
    start_date = None
    end_date = None
    state_filter = None
    customer_id = None

    if form.is_valid():
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        state_filter = form.cleaned_data.get('state_filter')
        cust = form.cleaned_data.get('customer')
        if cust:
            customer_id = cust.id

    invoices, summary = get_sales_register(
        start_date=start_date,
        end_date=end_date,
        state_filter=state_filter,
        customer_id=customer_id
    )

    context = {
        'form': form,
        'invoices': invoices,
        'summary': summary,
        'academic_disclaimer': True,
    }
    return render(request, 'finance/gst_sales_register.html', context)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'OWNER'])
def gst_monthly_summary_view(request):
    """
    Calendar Year Monthly GST Aggregation (Jan - Dec).
    Displays Taxable Turnover, CGST, SGST, IGST and Gross Sales per month.
    """
    form = MonthlyGSTFilterForm(request.GET)
    year = date.today().year
    if form.is_valid():
        y = form.cleaned_data.get('year')
        if y:
            year = y

    months_data, year_totals = get_monthly_gst_summary(year)

    context = {
        'form': form,
        'year': year,
        'months_data': months_data,
        'year_totals': year_totals,
        'academic_disclaimer': True,
    }
    return render(request, 'finance/gst_monthly_summary.html', context)


# ======================================================================
# 5. STOCK & PRODUCTION REPORTS
# ======================================================================

@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'PRODUCTION', 'OWNER'])
def stock_inventory_report_view(request):
    """
    Current Inventory Stock Report:
    - Raw Materials, Packaging, and Finished Goods Stock on Hand
    - Weighted-Average Unit Costs and Total Valuation
    - Reorder levels and low-stock alerts
    """
    form = StockFilterForm(request.GET)
    category = None
    if form.is_valid():
        category = form.cleaned_data.get('category')

    stock_data = get_current_stock_report(category=category)

    context = {
        'form': form,
        'category': category,
        'stock_data': stock_data,
    }
    return render(request, 'finance/stock_report.html', context)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'PRODUCTION', 'OWNER'])
def stock_ledger_report_view(request):
    """
    Traceable Stock Movement Ledger Report.
    Auditable chronological ledger of all opening balances, purchases,
    production issues, outputs, dispatches, and adjustments.
    """
    form = StockLedgerFilterForm(request.GET)
    start_date = None
    end_date = None
    movement_type = None
    item_type = None

    if form.is_valid():
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        movement_type = form.cleaned_data.get('movement_type')
        item_type = form.cleaned_data.get('item_type')

    ledger_entries = get_stock_movement_report(
        start_date=start_date,
        end_date=end_date,
        movement_type=movement_type,
        item_type=item_type
    )

    context = {
        'form': form,
        'ledger_entries': ledger_entries,
        'total_entries': len(ledger_entries),
    }
    return render(request, 'finance/stock_ledger_report.html', context)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'PRODUCTION', 'OWNER'])
def production_variance_report_view(request):
    """
    BOM-Based Production Consumption and Yield Variance Report.
    Tracks Planned vs Actual material consumption, 3% alerts, and cost per packet.
    """
    form = DateRangeFilterForm(request.GET)
    start_date = None
    end_date = None
    if form.is_valid():
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')

    runs = get_production_variance_report(start_date=start_date, end_date=end_date)

    context = {
        'form': form,
        'runs': runs,
        'total_runs': len(runs),
    }
    return render(request, 'finance/production_variance_report.html', context)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'SALESMAN', 'OWNER'])
def sales_dispatch_report_view(request):
    """
    Sales Dispatch Audit Report.
    Tracks dispatched sales orders, transport carriers, LR numbers, and dispatchers.
    """
    form = DateRangeFilterForm(request.GET)
    start_date = None
    end_date = None
    if form.is_valid():
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')

    dispatches = get_sales_dispatch_report(start_date=start_date, end_date=end_date)

    context = {
        'form': form,
        'dispatches': dispatches,
        'total_dispatches': len(dispatches),
    }
    return render(request, 'finance/sales_dispatch_report.html', context)


# ======================================================================
# 6. DATA EXPORT ENDPOINTS (CSV & EXCEL)
# ======================================================================

@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'OWNER'])
def export_sales_register_view(request):
    """
    Export GST Sales Register to CSV or Excel XML.
    """
    export_format = request.GET.get('format', 'excel').lower()
    start_date = _parse_date(request.GET.get('start_date'))
    end_date = _parse_date(request.GET.get('end_date'))
    state_filter = request.GET.get('state_filter')
    customer_id = request.GET.get('customer')

    invoices, summary = get_sales_register(
        start_date=start_date,
        end_date=end_date,
        state_filter=state_filter,
        customer_id=customer_id
    )

    headers = [
        'Invoice #', 'Invoice Date', 'Customer Name', 'State', 'GST Type',
        'Taxable (Rs)', 'CGST (Rs)', 'SGST (Rs)', 'IGST (Rs)',
        'Total Tax (Rs)', 'Grand Total (Rs)', 'Amount Paid (Rs)',
        'Balance Due (Rs)', 'Payment Status'
    ]

    rows = []
    for inv in invoices:
        gst_type = "Inter-State (5% IGST)" if inv.is_interstate else "Intra-State (2.5% CGST + 2.5% SGST)"
        rows.append([
            inv.invoice_number,
            inv.invoice_date.strftime('%Y-%m-%d'),
            inv.customer.name,
            inv.place_of_supply,
            gst_type,
            inv.taxable_amount,
            inv.cgst_amount,
            inv.sgst_amount,
            inv.igst_amount,
            inv.total_tax,
            inv.grand_total,
            inv.amount_paid,
            inv.balance_due,
            inv.get_payment_status_display(),
        ])

    filename = f"GST_Sales_Register_{date.today().strftime('%Y%m%d')}"

    if export_format == 'csv':
        return export_to_csv(filename, headers, rows)
    return export_to_excel_xml(filename, "Sales Register", headers, rows)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'OWNER'])
def export_receivables_view(request):
    """
    Export Customer Receivables Summary to CSV or Excel XML.
    """
    export_format = request.GET.get('format', 'excel').lower()
    summaries = get_customer_receivables_summary()

    headers = [
        'Customer Code', 'Customer Name', 'Customer Type', 'City', 'State',
        'Credit Days', 'Total Invoiced (Rs)', 'Total Received (Rs)',
        'Total Outstanding (Rs)', 'Open Invoices Count', 'Overdue Count',
        'Overdue Amount (Rs)'
    ]

    rows = []
    for s in summaries:
        c = s['customer']
        rows.append([
            c.code,
            c.name,
            c.get_customer_type_display(),
            c.city,
            c.state,
            s['credit_days'],
            s['total_invoiced'],
            s['total_received'],
            s['total_outstanding'],
            s['open_invoices_count'],
            s['overdue_count'],
            s['overdue_amount'],
        ])

    filename = f"Receivables_Summary_{date.today().strftime('%Y%m%d')}"

    if export_format == 'csv':
        return export_to_csv(filename, headers, rows)
    return export_to_excel_xml(filename, "Receivables", headers, rows)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'PRODUCTION', 'OWNER'])
def export_stock_summary_view(request):
    """
    Export Current Inventory Stock Balances to CSV or Excel XML.
    """
    export_format = request.GET.get('format', 'excel').lower()
    category = request.GET.get('category')
    stock_data = get_current_stock_report(category=category)

    headers = [
        'Category', 'Item Code', 'Item Name', 'Batch #',
        'Quantity on Hand', 'UOM', 'Unit Cost (Rs)', 'Total Valuation (Rs)',
        'Reorder Level', 'Low Stock Alert'
    ]

    rows = []
    all_items = stock_data['raw_materials'] + stock_data['packaging_materials'] + stock_data['finished_goods']
    for item in all_items:
        rows.append([
            item['item_type'],
            item['code'],
            item['name'],
            item['batch_number'],
            item['quantity_on_hand'],
            item['uom'],
            item['unit_cost'],
            item['total_valuation'],
            item['reorder_level'],
            "YES" if item['is_low_stock'] else "NO",
        ])

    filename = f"Inventory_Stock_Summary_{date.today().strftime('%Y%m%d')}"

    if export_format == 'csv':
        return export_to_csv(filename, headers, rows)
    return export_to_excel_xml(filename, "Stock Summary", headers, rows)


@login_required
@role_required(['ACCOUNTANT', 'AUDITOR', 'ADMIN', 'PRODUCTION', 'OWNER'])
def export_stock_ledger_view(request):
    """
    Export Traceable Stock Movement Ledger to CSV or Excel XML.
    """
    export_format = request.GET.get('format', 'excel').lower()
    start_date = _parse_date(request.GET.get('start_date'))
    end_date = _parse_date(request.GET.get('end_date'))
    movement_type = request.GET.get('movement_type')
    item_type = request.GET.get('item_type')

    entries = get_stock_movement_report(
        start_date=start_date,
        end_date=end_date,
        movement_type=movement_type,
        item_type=item_type
    )

    headers = [
        'Ledger ID', 'Date', 'Movement Type', 'Item Category', 'Item Name',
        'Batch #', 'Quantity Change', 'UOM', 'Unit Cost (Rs)', 'Balance After',
        'Source Reference', 'Performed By'
    ]

    rows = []
    for e in entries:
        user_name = e.performed_by.get_full_name() or e.performed_by.username if e.performed_by else 'System'
        source_ref = f"{e.reference_type}: {e.reference_id}" if e.reference_id else e.reference_type or '-'
        rows.append([
            e.entry_number or e.id,
            e.timestamp.strftime('%Y-%m-%d %H:%M'),
            e.get_movement_type_display(),
            e.get_item_type_display(),
            e.item_name,
            e.batch_number or '-',
            e.quantity_change,
            e.uom.code if e.uom else '',
            e.unit_cost,
            e.closing_quantity,
            source_ref,
            user_name,
        ])

    filename = f"Stock_Ledger_{date.today().strftime('%Y%m%d')}"

    if export_format == 'csv':
        return export_to_csv(filename, headers, rows)
    return export_to_excel_xml(filename, "Stock Ledger", headers, rows)
