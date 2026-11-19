from decimal import Decimal
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse

from apps.accounts.decorators import role_required, admin_required
from apps.accounts.models import CustomUser
from apps.inventory.models import StockItem
from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event
from .models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord
from .forms import (
    SalesOrderForm,
    SalesOrderItemFormSet,
    SalesOrderApprovalForm,
    SalesDispatchForm,
    PaymentRecordForm,
)
from .services import (
    generate_sales_order_number,
    check_order_stock_availability,
    approve_sales_order,
    reject_sales_order,
    generate_invoice_for_order,
    post_sales_dispatch,
    record_invoice_payment,
)
from .pdf_generator import generate_invoice_pdf


@login_required
def sales_dashboard_view(request):
    """
    Commercial Sales & Distribution Hub Dashboard.
    Provides KPIs: total orders, pending approval queue, dispatch ready, invoice receivables.
    """
    total_orders = SalesOrder.objects.count()
    pending_approval = SalesOrder.objects.filter(status=SalesOrder.Status.SUBMITTED).count()
    approved_orders = SalesOrder.objects.filter(status=SalesOrder.Status.APPROVED).count()
    invoiced_orders = SalesOrder.objects.filter(status=SalesOrder.Status.INVOICED).count()
    dispatched_orders = SalesOrder.objects.filter(status=SalesOrder.Status.DISPATCHED).count()

    total_revenue = SalesOrder.objects.filter(
        status__in=[SalesOrder.Status.INVOICED, SalesOrder.Status.DISPATCHED]
    ).aggregate(tot=Sum('total_amount'))['tot'] or Decimal('0.00')

    total_receivables = Invoice.objects.filter(
        payment_status__in=[Invoice.PaymentStatus.PENDING, Invoice.PaymentStatus.PARTIAL]
    )
    unpaid_balance = sum(inv.balance_due for inv in total_receivables)

    recent_orders = SalesOrder.objects.select_related(
        'customer', 'salesman'
    ).order_by('-created_at')[:8]

    recent_invoices = Invoice.objects.select_related(
        'customer', 'sales_order'
    ).order_by('-created_at')[:6]

    recent_dispatches = Dispatch.objects.select_related(
        'sales_order', 'invoice', 'dispatched_by'
    ).order_by('-created_at')[:6]

    context = {
        'total_orders': total_orders,
        'pending_approval': pending_approval,
        'approved_orders': approved_orders,
        'invoiced_orders': invoiced_orders,
        'dispatched_orders': dispatched_orders,
        'total_revenue': total_revenue,
        'unpaid_balance': unpaid_balance,
        'recent_orders': recent_orders,
        'recent_invoices': recent_invoices,
        'recent_dispatches': recent_dispatches,
    }
    return render(request, 'sales/dashboard.html', context)


@login_required
def sales_order_list_view(request):
    """
    List view for all Sales Orders with filters by status, customer, date and search query.
    """
    orders_qs = SalesOrder.objects.select_related('customer', 'salesman').all()

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        orders_qs = orders_qs.filter(
            Q(order_number__icontains=q) |
            Q(customer__name__icontains=q) |
            Q(customer__code__icontains=q) |
            Q(delivery_city__icontains=q)
        )

    # Status filter
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        orders_qs = orders_qs.filter(status=status_filter)

    # If user is a Salesman and not admin/auditor, optionally show salesman's orders
    salesman_filter = request.GET.get('salesman', '').strip()
    if salesman_filter:
        orders_qs = orders_qs.filter(salesman_id=salesman_filter)

    paginator = Paginator(orders_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'orders': page_obj.object_list,
        'status_choices': SalesOrder.Status.choices,
        'current_status': status_filter,
        'search_query': q,
    }
    return render(request, 'sales/order_list.html', context)


@login_required
@role_required(['SALESMAN', 'ADMIN', 'OWNER'])
def sales_order_create_view(request):
    """
    Creation of new Sales Order by Sales Representatives or Admins.
    Supports dynamic line items with pack sizes, quantities, and prices.
    """
    if request.method == 'POST':
        form = SalesOrderForm(request.POST)
        formset = SalesOrderItemFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.order_number = generate_sales_order_number()
            order.salesman = request.user
            order.status = SalesOrder.Status.DRAFT

            # Check if user clicked 'Submit for Approval'
            submit_action = request.POST.get('submit_action') == 'submit_for_approval'
            if submit_action:
                order.status = SalesOrder.Status.SUBMITTED

            order.save()
            formset.instance = order
            formset.save()

            # Recalculate intra-state vs inter-state taxes and grand totals
            order.update_totals()

            log_audit_event(
                action=AuditLogEntry.Action.ORDER_CREATED,
                module=AuditLogEntry.Module.SALES,
                object_repr=f"Sales Order {order.order_number}",
                object_id=str(order.pk),
                reference_number=order.order_number,
                user=request.user,
                request=request,
                details={
                    'customer': order.customer.name,
                    'status': order.status,
                    'total_amount': order.total_amount,
                    'items_count': order.items.count()
                }
            )

            if submit_action:
                messages.success(
                    request,
                    f"Sales Order {order.order_number} created and submitted for Admin verification & approval."
                )
            else:
                messages.success(
                    request,
                    f"Sales Order {order.order_number} saved as Draft. You can edit line items before submitting."
                )
            return redirect('sales_order_detail', pk=order.pk)
    else:
        form = SalesOrderForm()
        formset = SalesOrderItemFormSet()

    context = {
        'form': form,
        'formset': formset,
        'title': 'Create New Sales Order',
    }
    return render(request, 'sales/order_create.html', context)


@login_required
@role_required(['SALESMAN', 'ADMIN', 'OWNER'])
def sales_order_edit_view(request, pk):
    """
    Edit existing Sales Order (only permitted when DRAFT or REJECTED).
    """
    order = get_object_or_404(SalesOrder, pk=pk)

    if order.status not in [SalesOrder.Status.DRAFT, SalesOrder.Status.REJECTED]:
        messages.error(request, f"Sales Order {order.order_number} is in '{order.get_status_display()}' status and cannot be edited.")
        return redirect('sales_order_detail', pk=order.pk)

    if request.method == 'POST':
        form = SalesOrderForm(request.POST, instance=order)
        formset = SalesOrderItemFormSet(request.POST, instance=order)

        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            submit_action = request.POST.get('submit_action') == 'submit_for_approval'
            if submit_action:
                order.status = SalesOrder.Status.SUBMITTED
                order.rejection_reason = ''

            order.save()
            formset.save()
            order.update_totals()

            if submit_action:
                messages.success(request, f"Sales Order {order.order_number} updated and submitted for approval.")
            else:
                messages.success(request, f"Sales Order {order.order_number} changes saved successfully.")
            return redirect('sales_order_detail', pk=order.pk)
    else:
        form = SalesOrderForm(instance=order)
        formset = SalesOrderItemFormSet(instance=order)

    context = {
        'form': form,
        'formset': formset,
        'order': order,
        'title': f'Edit Sales Order {order.order_number}',
    }
    return render(request, 'sales/order_create.html', context)


@login_required
def sales_order_detail_view(request, pk):
    """
    Comprehensive Order-to-Audit view for a Sales Order.
    Displays customer data, line items with GST breakups, stock availability checks,
    admin verification controls, and invoice/dispatch statuses.
    """
    order = get_object_or_404(
        SalesOrder.objects.select_related('customer', 'salesman', 'approved_by'),
        pk=pk
    )
    items = list(order.items.select_related('product_pack_size__product', 'uom').all())

    # Calculate stock availability for each item
    items_with_stock = []
    overall_stock_available = True

    for item in items:
        stock_qs = StockItem.objects.filter(
            product_pack_size=item.product_pack_size,
            quantity_on_hand__gt=0
        )
        total_on_hand = sum(s.quantity_on_hand for s in stock_qs)
        is_sufficient = total_on_hand >= item.quantity
        if not is_sufficient:
            overall_stock_available = False

        items_with_stock.append({
            'item': item,
            'on_hand': total_on_hand,
            'is_sufficient': is_sufficient,
            'shortfall': max(Decimal('0.00'), item.quantity - total_on_hand),
        })

    approval_form = SalesOrderApprovalForm()
    dispatch_form = SalesDispatchForm()

    context = {
        'order': order,
        'items_with_stock': items_with_stock,
        'overall_stock_available': overall_stock_available,
        'approval_form': approval_form,
        'dispatch_form': dispatch_form,
        'can_approve': request.user.role == CustomUser.Role.ADMIN or request.user.is_superuser,
        'can_edit': order.status in [SalesOrder.Status.DRAFT, SalesOrder.Status.REJECTED],
    }
    return render(request, 'sales/order_detail.html', context)


@login_required
@role_required(['SALESMAN', 'ADMIN', 'OWNER'])
def sales_order_submit_view(request, pk):
    """Submits a DRAFT order for Admin verification & approval."""
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('sales_order_detail', kwargs={'pk': pk}))

    order = get_object_or_404(SalesOrder, pk=pk)
    if order.status != SalesOrder.Status.DRAFT:
        messages.warning(request, f"Order {order.order_number} is already in {order.get_status_display()} status.")
        return redirect('sales_order_detail', pk=order.pk)

    if not order.items.exists():
        messages.error(request, "Cannot submit an empty order. Please add at least one line item.")
        return redirect('sales_order_detail', pk=order.pk)

    order.status = SalesOrder.Status.SUBMITTED
    order.save(update_fields=['status', 'updated_at'])
    messages.success(request, f"Sales Order {order.order_number} has been submitted for Admin verification.")
    return redirect('sales_order_detail', pk=order.pk)


@login_required
@role_required(['ADMIN'])
def sales_order_approve_view(request, pk):
    """Admin verifies and approves a Sales Order after validating stock availability."""
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('sales_order_detail', kwargs={'pk': pk}))

    try:
        order = approve_sales_order(pk, request.user)
        messages.success(request, f"Sales Order {order.order_number} verified and APPROVED successfully.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))
    except Exception as e:
        messages.error(request, f"Error approving order: {e}")

    return redirect('sales_order_detail', pk=pk)


@login_required
@role_required(['ADMIN'])
def sales_order_reject_view(request, pk):
    """Admin rejects a Sales Order with mandatory recorded reason."""
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('sales_order_detail', kwargs={'pk': pk}))

    reason = request.POST.get('rejection_reason', '').strip()
    if not reason:
        messages.error(request, "A reason is mandatory when rejecting a sales order.")
        return redirect('sales_order_detail', pk=pk)

    try:
        order = reject_sales_order(pk, request.user, reason)
        messages.warning(request, f"Sales Order {order.order_number} has been REJECTED. Reason recorded.")
    except Exception as e:
        messages.error(request, f"Error rejecting order: {e}")

    return redirect('sales_order_detail', pk=pk)


@login_required
@role_required(['ADMIN', 'SALESMAN', 'OWNER'])
def invoice_generate_view(request, order_pk):
    """Generates official Tax Invoice for an approved Sales Order."""
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('sales_order_detail', kwargs={'pk': order_pk}))

    try:
        invoice = generate_invoice_for_order(order_pk, request.user)
        messages.success(request, f"Official Tax Invoice {invoice.invoice_number} generated successfully.")
        return redirect('invoice_detail', pk=invoice.pk)
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))
        return redirect('sales_order_detail', pk=order_pk)
    except Exception as e:
        messages.error(request, f"Error generating invoice: {e}")
        return redirect('sales_order_detail', pk=order_pk)


@login_required
def invoice_list_view(request):
    """List of all generated GST Tax Invoices."""
    invoices_qs = Invoice.objects.select_related('customer', 'sales_order').all()

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        invoices_qs = invoices_qs.filter(
            Q(invoice_number__icontains=q) |
            Q(customer_name__icontains=q) |
            Q(customer_gstin__icontains=q) |
            Q(sales_order__order_number__icontains=q)
        )

    # Status filter
    status_filter = request.GET.get('payment_status', '').strip()
    if status_filter:
        invoices_qs = invoices_qs.filter(payment_status=status_filter)

    paginator = Paginator(invoices_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'invoices': page_obj.object_list,
        'payment_status_choices': Invoice.PaymentStatus.choices,
        'current_status': status_filter,
        'search_query': q,
    }
    return render(request, 'sales/invoice_list.html', context)


@login_required
def invoice_detail_view(request, pk):
    """Detailed view of a Tax Invoice with payment recording capabilities."""
    invoice = get_object_or_404(
        Invoice.objects.select_related('sales_order', 'customer', 'created_by'),
        pk=pk
    )
    payments = invoice.payments.select_related('recorded_by').order_by('-payment_date')
    payment_form = PaymentRecordForm(initial={'amount': invoice.balance_due})

    context = {
        'invoice': invoice,
        'order': invoice.sales_order,
        'payments': payments,
        'payment_form': payment_form,
    }
    return render(request, 'sales/invoice_detail.html', context)


@login_required
def invoice_pdf_view(request, pk):
    """
    Downloads or views the official GST Tax Invoice as a binary PDF 1.4 document.
    """
    invoice = get_object_or_404(
        Invoice.objects.select_related('sales_order', 'customer'),
        pk=pk
    )
    pdf_bytes = generate_invoice_pdf(invoice)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"Tax-Invoice-{invoice.invoice_number}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
def dispatch_list_view(request):
    """List of all goods dispatches with carrier and tracking info."""
    dispatches_qs = Dispatch.objects.select_related(
        'sales_order', 'invoice', 'dispatched_by'
    ).all()

    q = request.GET.get('q', '').strip()
    if q:
        dispatches_qs = dispatches_qs.filter(
            Q(dispatch_number__icontains=q) |
            Q(sales_order__order_number__icontains=q) |
            Q(carrier_name__icontains=q) |
            Q(lr_number__icontains=q) |
            Q(vehicle_number__icontains=q)
        )

    paginator = Paginator(dispatches_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'dispatches': page_obj.object_list,
        'search_query': q,
    }
    return render(request, 'sales/dispatch_list.html', context)


@login_required
@role_required(['ADMIN', 'PRODUCTION', 'OWNER'])
def dispatch_create_view(request, order_pk):
    """
    Executes goods dispatch for an approved sales order.
    Deducts finished stock from StockLedgerEntry and advances order status to DISPATCHED.
    """
    order = get_object_or_404(SalesOrder, pk=order_pk)

    if request.method == 'POST':
        form = SalesDispatchForm(request.POST)
        if form.is_valid():
            try:
                dispatch = post_sales_dispatch(
                    sales_order_id=order.pk,
                    user=request.user,
                    carrier_name=form.cleaned_data['carrier_name'],
                    vehicle_number=form.cleaned_data['vehicle_number'],
                    lr_number=form.cleaned_data['lr_number'],
                    notes=form.cleaned_data['notes']
                )
                messages.success(
                    request,
                    f"Dispatch {dispatch.dispatch_number} posted successfully! "
                    f"Finished goods stock deducted from warehouse ledger."
                )
                return redirect('sales_order_detail', pk=order.pk)
            except ValidationError as e:
                messages.error(request, str(e.message if hasattr(e, 'message') else e))
            except Exception as e:
                messages.error(request, f"Error processing dispatch: {e}")
    else:
        form = SalesDispatchForm()

    context = {
        'order': order,
        'form': form,
    }
    return render(request, 'sales/dispatch_create.html', context)


@login_required
@role_required(['ADMIN', 'OWNER', 'SALESMAN'])
def payment_record_create_view(request, invoice_pk):
    """Records payment remittance against an outstanding invoice."""
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('invoice_detail', kwargs={'pk': invoice_pk}))

    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    form = PaymentRecordForm(request.POST)

    if form.is_valid():
        try:
            payment = record_invoice_payment(
                invoice_id=invoice.pk,
                amount=form.cleaned_data['amount'],
                payment_mode=form.cleaned_data['payment_mode'],
                reference_no=form.cleaned_data['transaction_reference'],
                user=request.user,
                notes=form.cleaned_data['notes']
            )
            messages.success(
                request,
                f"Payment receipt {payment.payment_number} for ₹{payment.amount} recorded successfully. "
                f"Invoice status is now {invoice.get_payment_status_display()}."
            )
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, 'message') else e))
        except Exception as e:
            messages.error(request, f"Error recording payment: {e}")
    else:
        messages.error(request, "Invalid payment details submitted.")

    return redirect('invoice_detail', pk=invoice.pk)
