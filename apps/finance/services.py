from decimal import Decimal
from datetime import date, datetime
import csv
import io
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import HttpResponse

from apps.master_data.models import Customer, ProductPackSize, RawMaterial, PackagingMaterial
from apps.inventory.models import StockItem, StockLedgerEntry, ItemType, MovementType
from apps.production.models import ProductionRun, ProductionMaterialConsumption
from apps.sales.models import SalesOrder, Invoice, Dispatch, PaymentRecord


def get_receivables_summary():
    """
    Computes system-wide receivables KPIs:
    - Total Invoiced, Total Received, Total Outstanding
    - Counts of Pending, Partial, and Paid invoices
    - Overdue invoices count and overdue balance
    """
    invoices = Invoice.objects.select_related('customer').all()
    today = date.today()

    total_invoiced = Decimal('0.00')
    total_received = Decimal('0.00')
    total_outstanding = Decimal('0.00')
    pending_count = 0
    partial_count = 0
    paid_count = 0
    overdue_count = 0
    overdue_amount = Decimal('0.00')

    for inv in invoices:
        total_invoiced += inv.grand_total
        total_received += inv.amount_paid
        bal = inv.balance_due
        total_outstanding += bal

        if inv.payment_status == Invoice.PaymentStatus.PAID:
            paid_count += 1
        elif inv.payment_status == Invoice.PaymentStatus.PARTIAL:
            partial_count += 1
        else:
            pending_count += 1

        if inv.due_date and inv.due_date < today and bal > Decimal('0.00'):
            overdue_count += 1
            overdue_amount += bal

    return {
        'total_invoiced': total_invoiced,
        'total_received': total_received,
        'total_outstanding': total_outstanding,
        'total_invoices_count': len(invoices),
        'pending_count': pending_count,
        'partial_count': partial_count,
        'paid_count': paid_count,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
    }


def get_customer_receivables_summary():
    """
    Groups receivables by customer:
    Returns list of dicts with customer details, total invoiced, received, balance due, and overdue amounts.
    """
    today = date.today()
    customers = Customer.objects.filter(is_active=True).prefetch_related('invoices').order_by('name')
    result = []

    for cust in customers:
        invoices = list(cust.invoices.all())
        if not invoices:
            continue

        cust_invoiced = sum(i.grand_total for i in invoices)
        cust_received = sum(i.amount_paid for i in invoices)
        cust_balance = sum(i.balance_due for i in invoices)
        open_count = sum(1 for i in invoices if i.balance_due > 0)
        overdue_invoices = [i for i in invoices if i.due_date and i.due_date < today and i.balance_due > 0]
        overdue_amt = sum(i.balance_due for i in overdue_invoices)

        result.append({
            'customer': cust,
            'total_invoiced': cust_invoiced,
            'total_received': cust_received,
            'total_outstanding': cust_balance,
            'invoices_count': len(invoices),
            'open_invoices_count': open_count,
            'overdue_count': len(overdue_invoices),
            'overdue_amount': overdue_amt,
            'credit_limit': cust.credit_limit,
            'credit_days': cust.credit_days,
        })

    # Sort by highest outstanding balance first
    result.sort(key=lambda x: x['total_outstanding'], reverse=True)
    return result


def get_overdue_invoices():
    """Returns list of all overdue invoices with outstanding balances."""
    today = date.today()
    return Invoice.objects.filter(
        due_date__lt=today
    ).exclude(
        payment_status=Invoice.PaymentStatus.PAID
    ).select_related('customer', 'sales_order').order_by('due_date')


def get_sales_register(start_date=None, end_date=None, state_filter=None, customer_id=None):
    """
    Generates Sales Register with detailed GST breakups:
    - Intra-state (Tamil Nadu: 2.5% CGST + 2.5% SGST)
    - Inter-state (Outside Tamil Nadu: 5% IGST)
    - Summary totals
    """
    invoices_qs = Invoice.objects.select_related('customer', 'sales_order').all()

    if start_date:
        invoices_qs = invoices_qs.filter(invoice_date__gte=start_date)
    if end_date:
        invoices_qs = invoices_qs.filter(invoice_date__lte=end_date)
    if state_filter == 'INTRA':
        invoices_qs = invoices_qs.filter(is_interstate=False)
    elif state_filter == 'INTER':
        invoices_qs = invoices_qs.filter(is_interstate=True)
    if customer_id:
        invoices_qs = invoices_qs.filter(customer_id=customer_id)

    invoices = list(invoices_qs.order_by('-invoice_date', '-created_at'))

    summary = {
        'total_taxable': sum(i.taxable_amount for i in invoices),
        'total_cgst': sum(i.cgst_amount for i in invoices),
        'total_sgst': sum(i.sgst_amount for i in invoices),
        'total_igst': sum(i.igst_amount for i in invoices),
        'total_tax': sum(i.total_tax for i in invoices),
        'grand_total': sum(i.grand_total for i in invoices),
        'total_paid': sum(i.amount_paid for i in invoices),
        'total_due': sum(i.balance_due for i in invoices),
        'intra_count': sum(1 for i in invoices if not i.is_interstate),
        'inter_count': sum(1 for i in invoices if i.is_interstate),
        'total_count': len(invoices),
    }

    return invoices, summary


def get_monthly_gst_summary(year=None):
    """
    Aggregates GST tax collections and taxable value by month for a given calendar year.
    Returns: list of dicts per month (Jan-Dec) with totals.
    """
    if not year:
        year = date.today().year

    invoices = Invoice.objects.filter(invoice_date__year=year)
    months_data = []

    month_names = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]

    for month_num in range(1, 13):
        m_invoices = [i for i in invoices if i.invoice_date.month == month_num]
        taxable = sum(i.taxable_amount for i in m_invoices)
        cgst = sum(i.cgst_amount for i in m_invoices)
        sgst = sum(i.sgst_amount for i in m_invoices)
        igst = sum(i.igst_amount for i in m_invoices)
        total_tax = sum(i.total_tax for i in m_invoices)
        grand = sum(i.grand_total for i in m_invoices)

        months_data.append({
            'month_num': month_num,
            'month_name': month_names[month_num - 1],
            'invoices_count': len(m_invoices),
            'taxable_amount': taxable,
            'cgst_amount': cgst,
            'sgst_amount': sgst,
            'igst_amount': igst,
            'total_tax': total_tax,
            'grand_total': grand,
        })

    year_totals = {
        'taxable_amount': sum(m['taxable_amount'] for m in months_data),
        'cgst_amount': sum(m['cgst_amount'] for m in months_data),
        'sgst_amount': sum(m['sgst_amount'] for m in months_data),
        'igst_amount': sum(m['igst_amount'] for m in months_data),
        'total_tax': sum(m['total_tax'] for m in months_data),
        'grand_total': sum(m['grand_total'] for m in months_data),
        'invoices_count': sum(m['invoices_count'] for m in months_data),
    }

    return months_data, year_totals


def get_current_stock_report(category=None):
    """
    Retrieves current stock on hand across raw materials, packaging materials, and finished goods.
    """
    stock_qs = StockItem.objects.select_related(
        'raw_material__uom',
        'packaging_material__uom',
        'product_pack_size__product',
        'product_pack_size__uom'
    ).order_by('item_type', 'id')

    if category:
        stock_qs = stock_qs.filter(item_type=category)

    raw_items = []
    pkg_items = []
    fg_items = []

    for item in stock_qs:
        reorder_lvl = Decimal('0.00')
        if item.item_type == ItemType.RAW_MATERIAL and item.raw_material:
            reorder_lvl = item.raw_material.reorder_level
        elif item.item_type == ItemType.PACKAGING_MATERIAL and item.packaging_material:
            reorder_lvl = item.packaging_material.reorder_level

        entry = {
            'stock_item': item,
            'item_type': item.get_item_type_display(),
            'code': item.item_code,
            'name': item.item_name,
            'batch_number': item.batch_number or '-',
            'quantity_on_hand': item.quantity_on_hand,
            'uom': item.uom.code if item.uom else '',
            'unit_cost': item.unit_cost,
            'total_valuation': (item.quantity_on_hand * item.unit_cost).quantize(Decimal('0.01')),
            'reorder_level': reorder_lvl,
            'is_low_stock': item.is_low_stock,
        }
        if item.item_type == ItemType.RAW_MATERIAL:
            raw_items.append(entry)
        elif item.item_type == ItemType.PACKAGING_MATERIAL:
            pkg_items.append(entry)
        elif item.item_type == ItemType.FINISHED_GOODS:
            fg_items.append(entry)

    total_valuation = sum(item['total_valuation'] for item in (raw_items + pkg_items + fg_items))

    return {
        'raw_materials': raw_items,
        'packaging_materials': pkg_items,
        'finished_goods': fg_items,
        'total_valuation': total_valuation,
        'raw_valuation': sum(r['total_valuation'] for r in raw_items),
        'pkg_valuation': sum(p['total_valuation'] for p in pkg_items),
        'fg_valuation': sum(f['total_valuation'] for f in fg_items),
    }


def get_stock_movement_report(start_date=None, end_date=None, movement_type=None, item_type=None):
    """Retrieves chronological stock ledger movements with audit sources."""
    ledger_qs = StockLedgerEntry.objects.select_related(
        'raw_material', 'packaging_material', 'product_pack_size__product', 'uom', 'performed_by'
    ).order_by('-timestamp', '-id')

    if start_date:
        ledger_qs = ledger_qs.filter(timestamp__date__gte=start_date)
    if end_date:
        ledger_qs = ledger_qs.filter(timestamp__date__lte=end_date)
    if movement_type:
        ledger_qs = ledger_qs.filter(movement_type=movement_type)
    if item_type:
        ledger_qs = ledger_qs.filter(item_type=item_type)

    return list(ledger_qs)


def get_production_variance_report(start_date=None, end_date=None):
    """Retrieves production execution runs with BOM variances and costing."""
    runs_qs = ProductionRun.objects.select_related(
        'product', 'product_pack_size', 'bill_of_materials', 'created_by'
    ).prefetch_related('materials__raw_material', 'materials__packaging_material', 'materials__uom').order_by('-manufacture_date')

    if start_date:
        runs_qs = runs_qs.filter(manufacture_date__gte=start_date)
    if end_date:
        runs_qs = runs_qs.filter(manufacture_date__lte=end_date)

    return list(runs_qs)


def get_sales_dispatch_report(start_date=None, end_date=None):
    """Retrieves dispatch logs with logistics carriers and order references."""
    disp_qs = Dispatch.objects.select_related(
        'sales_order__customer', 'invoice', 'dispatched_by'
    ).order_by('-dispatch_date', '-created_at')

    if start_date:
        disp_qs = disp_qs.filter(dispatch_date__gte=start_date)
    if end_date:
        disp_qs = disp_qs.filter(dispatch_date__lte=end_date)

    return list(disp_qs)


# ======================================================================
# DATA EXPORT UTILITIES (CSV & PURE-PYTHON EXCEL XML SPREADSHEET)
# ======================================================================

def export_to_csv(filename, headers, rows):
    """
    Streams data as a downloadable RFC 4180 CSV with UTF-8 BOM (\ufeff)
    for seamless compatibility with Microsoft Excel and Google Sheets.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)

    response = HttpResponse(output.getvalue().encode('utf-8-sig'), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    return response


def export_to_excel_xml(filename, sheet_name, headers, rows):
    """
    Streams data as a valid Microsoft Excel XML Spreadsheet 2003 (.xls).
    Natively opens in Microsoft Excel, LibreOffice, and Google Sheets without external packages.
    """
    def _escape_xml(val):
        if val is None:
            return ""
        s = str(val)
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<?mso-application progid="Excel.Sheet"?>')
    xml.append('<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" '
               'xmlns:o="urn:schemas-microsoft-com:office:office" '
               'xmlns:x="urn:schemas-microsoft-com:office:excel" '
               'xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet" '
               'xmlns:html="http://www.w3.org/TR/REC-html40">')

    # Styles
    xml.append('<Styles>')
    xml.append('  <Style ss:ID="Header">')
    xml.append('    <Font ss:Bold="1" ss:Color="#FFFFFF"/>')
    xml.append('    <Interior ss:Color="#1B365D" ss:Pattern="Solid"/>')
    xml.append('    <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>')
    xml.append('  </Style>')
    xml.append('  <Style ss:ID="Number">')
    xml.append('    <NumberFormat ss:Format="#,##0.00"/>')
    xml.append('    <Alignment ss:Horizontal="Right"/>')
    xml.append('  </Style>')
    xml.append('  <Style ss:ID="Integer">')
    xml.append('    <NumberFormat ss:Format="#,##0"/>')
    xml.append('    <Alignment ss:Horizontal="Right"/>')
    xml.append('  </Style>')
    xml.append('  <Style ss:ID="Default">')
    xml.append('    <Alignment ss:Vertical="Center"/>')
    xml.append('  </Style>')
    xml.append('</Styles>')

    # Worksheet
    clean_sheet_name = _escape_xml(sheet_name[:30] or "Sheet1")
    xml.append(f'<Worksheet ss:Name="{clean_sheet_name}">')
    xml.append('<Table>')

    # Header Row
    xml.append('  <Row ss:StyleID="Header">')
    for h in headers:
        xml.append(f'    <Cell><Data ss:Type="String">{_escape_xml(h)}</Data></Cell>')
    xml.append('  </Row>')

    # Data Rows
    for row in rows:
        xml.append('  <Row>')
        for cell in row:
            if isinstance(cell, (int,)):
                xml.append(f'    <Cell ss:StyleID="Integer"><Data ss:Type="Number">{cell}</Data></Cell>')
            elif isinstance(cell, (float, Decimal)):
                xml.append(f'    <Cell ss:StyleID="Number"><Data ss:Type="Number">{cell:.2f}</Data></Cell>')
            else:
                xml.append(f'    <Cell ss:StyleID="Default"><Data ss:Type="String">{_escape_xml(cell)}</Data></Cell>')
        xml.append('  </Row>')

    xml.append('</Table>')
    xml.append('</Worksheet>')
    xml.append('</Workbook>')

    content = "\n".join(xml)
    response = HttpResponse(content.encode('utf-8'), content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{filename}.xls"'
    return response
