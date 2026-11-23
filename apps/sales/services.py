from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.master_data.models import Customer, ProductPackSize
from apps.inventory.models import ItemType, MovementType, StockItem, StockLedgerEntry
from apps.inventory.services import record_stock_movement
from apps.core.models import AuditLogEntry
from apps.core.audit import log_audit_event
from .models import SalesOrder, SalesOrderItem, Invoice, Dispatch, PaymentRecord


def generate_sales_order_number():
    now = timezone.now()
    timestamp_str = now.strftime('%Y%m%d%H%M%S%f')
    return f"SO-{timestamp_str[:17]}"


def generate_invoice_number():
    now = timezone.now()
    timestamp_str = now.strftime('%Y%m%d%H%M%S%f')
    return f"INV-{timestamp_str[:17]}"


def generate_dispatch_number():
    now = timezone.now()
    timestamp_str = now.strftime('%Y%m%d%H%M%S%f')
    return f"DSP-{timestamp_str[:17]}"


def generate_payment_number():
    now = timezone.now()
    timestamp_str = now.strftime('%Y%m%d%H%M%S%f')
    return f"PAY-{timestamp_str[:17]}"


def check_order_stock_availability(sales_order):
    """
    Validates whether there is sufficient finished goods stock on hand to fulfill the order.
    Returns: (is_available: bool, item: SalesOrderItem or None, available_qty: Decimal, required_qty: Decimal)
    """
    first_item = None
    total_avail = Decimal('0.00')
    total_req = Decimal('0.00')

    for item in sales_order.items.all():
        if first_item is None:
            first_item = item
        stock_qs = StockItem.objects.filter(
            product_pack_size=item.product_pack_size,
            quantity_on_hand__gt=0
        )
        total_on_hand = sum(s.quantity_on_hand for s in stock_qs)
        if total_on_hand < item.quantity:
            return False, item, total_on_hand, item.quantity
        total_avail += total_on_hand
        total_req += item.quantity

    return True, first_item, total_avail, total_req


def get_order_stock_shortage(sales_order):
    """
    Returns stock shortage details for a sales order:
    (shortage_qty: Decimal, is_short: bool, available_qty: Decimal, required_qty: Decimal)
    """
    is_avail, item, on_hand, req = check_order_stock_availability(sales_order)
    if not is_avail:
        return (req - on_hand), True, on_hand, req
    return Decimal('0.00'), False, on_hand, req


@transaction.atomic
def approve_sales_order(sales_order_id, admin_user):
    """
    Admin verifies and approves a submitted Sales Order.
    Validates finished goods stock availability prior to approval.
    """
    if admin_user.role != CustomUser.Role.ADMIN and not admin_user.is_superuser:
        raise ValidationError("Only System Administrators can verify and approve sales orders.")

    order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)

    if order.status not in [SalesOrder.Status.SUBMITTED, SalesOrder.Status.DRAFT]:
        raise ValidationError(f"Order {order.order_number} cannot be approved from its current status: {order.get_status_display()}.")

    # Validate stock availability
    is_avail, item, on_hand, req = check_order_stock_availability(order)
    if not is_avail:
        shortage = req - on_hand
        raise ValidationError(
            f"Cannot approve order {order.order_number}: Insufficient finished goods stock! "
            f"Item: {item.item_name}, Required: {req} {item.uom.code}, Available on hand: {on_hand} {item.uom.code}, "
            f"Shortage: {shortage} {item.uom.code}. Negative inventory is strictly prohibited."
        )

    order.status = SalesOrder.Status.APPROVED
    order.approved_by = admin_user
    order.approved_at = timezone.now()
    order.rejection_reason = ''
    order.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])

    log_audit_event(
        action=AuditLogEntry.Action.ORDER_APPROVED,
        module=AuditLogEntry.Module.SALES,
        object_repr=f"Sales Order {order.order_number}",
        object_id=str(order.pk),
        reference_number=order.order_number,
        user=admin_user,
        details={
            'customer': order.customer.name,
            'total_amount': order.total_amount,
            'delivery_state': order.delivery_state,
            'is_interstate': order.is_interstate
        }
    )
    return order


@transaction.atomic
def reject_sales_order(sales_order_id, admin_user, reason=''):
    """
    Admin rejects a Sales Order with a mandatory or recorded reason.
    """
    if admin_user.role != CustomUser.Role.ADMIN and not admin_user.is_superuser:
        raise ValidationError("Only System Administrators can reject sales orders.")

    order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)
    order.status = SalesOrder.Status.REJECTED
    order.approved_by = admin_user
    order.approved_at = timezone.now()
    order.rejection_reason = reason or 'Rejected by Administrator during order review.'
    order.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason', 'updated_at'])

    log_audit_event(
        action=AuditLogEntry.Action.ORDER_REJECTED,
        module=AuditLogEntry.Module.SALES,
        object_repr=f"Sales Order {order.order_number}",
        object_id=str(order.pk),
        reference_number=order.order_number,
        user=admin_user,
        details={
            'customer': order.customer.name,
            'total_amount': order.total_amount,
            'rejection_reason': order.rejection_reason
        }
    )
    return order


@transaction.atomic
def generate_invoice_for_order(sales_order_id, user, allow_unapproved=False):
    """
    Generates official Tax Invoice for an approved Sales Order:
    - Accurate GST rates based on state:
      * Intra-state (Tamil Nadu): 2.5% CGST + 2.5% SGST
      * Inter-state: 5% IGST
    - Computes totals and advances status to INVOICED.
    - Prevents duplicate invoice creation.
    """
    if hasattr(sales_order_id, 'id'):
        sales_order_id = sales_order_id.id
    order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)

    # Check if invoice already exists - duplicate invoice generation prohibited
    if hasattr(order, 'invoice') and order.invoice:
        raise ValidationError(
            f"Tax Invoice {order.invoice.invoice_number} has already been generated for Sales Order {order.order_number}. "
            f"Duplicate invoice generation is prohibited."
        )

    if order.status not in [SalesOrder.Status.APPROVED, SalesOrder.Status.INVOICED] and not allow_unapproved:
        raise ValidationError(f"Cannot generate invoice: Order must be in APPROVED status (currently {order.get_status_display()}).")

    # Ensure financial totals are up to date
    order.update_totals()

    customer = order.customer
    inv_num = generate_invoice_number()
    due_dt = order.order_date + timedelta(days=customer.credit_days or 30)

    # Place of supply & interstate logic
    place_of_supply = order.delivery_state or customer.state or 'Tamil Nadu'
    is_interstate = order.is_interstate

    payment_terms_desc = f"Net {customer.credit_days} Days" if getattr(customer, 'credit_days', None) else "Net 30 Days"
    invoice = Invoice.objects.create(
        invoice_number=inv_num,
        sales_order=order,
        customer=customer,
        invoice_date=date.today(),
        due_date=due_dt,
        company_name='ManuFlow Foods & Processing Operations',
        company_gstin='33NITTRICHY1Z5 (Demo Environment)',
        company_address='Food Processing Industrial Estate, Thuvakudi, Tiruchirappalli - 620015, Tamil Nadu',
        company_state='Tamil Nadu',
        company_state_code='33',
        customer_name=customer.name,
        customer_gstin=customer.tax_id_gst,
        billing_address=customer.billing_address,
        shipping_address=order.delivery_address or customer.shipping_address,
        place_of_supply=place_of_supply,
        is_interstate=is_interstate,
        taxable_amount=order.subtotal_amount - order.discount_amount,
        cgst_rate_pct=Decimal('0.00') if is_interstate else Decimal('2.50'),
        cgst_amount=Decimal('0.00') if is_interstate else order.cgst_amount,
        sgst_rate_pct=Decimal('0.00') if is_interstate else Decimal('2.50'),
        sgst_amount=Decimal('0.00') if is_interstate else order.sgst_amount,
        igst_rate_pct=Decimal('5.00') if is_interstate else Decimal('0.00'),
        igst_amount=order.igst_amount if is_interstate else Decimal('0.00'),
        total_tax=order.total_tax_amount,
        grand_total=order.total_amount,
        payment_status=Invoice.PaymentStatus.PENDING,
        amount_paid=Decimal('0.00'),
        created_by=user,
        notes=f"Generated for Sales Order {order.order_number}. Payment terms: {payment_terms_desc}."
    )

    if order.status != SalesOrder.Status.DISPATCHED:
        order.status = SalesOrder.Status.INVOICED
        order.save(update_fields=['status', 'updated_at'])

    log_audit_event(
        action=AuditLogEntry.Action.INVOICE_GENERATED,
        module=AuditLogEntry.Module.SALES,
        object_repr=f"Tax Invoice {invoice.invoice_number}",
        object_id=str(invoice.pk),
        reference_number=invoice.invoice_number,
        user=user,
        details={
            'sales_order': order.order_number,
            'customer': order.customer.name,
            'taxable_amount': invoice.taxable_amount,
            'cgst_amount': invoice.cgst_amount,
            'sgst_amount': invoice.sgst_amount,
            'igst_amount': invoice.igst_amount,
            'total_tax': invoice.total_tax,
            'grand_total': invoice.grand_total,
            'is_interstate': invoice.is_interstate
        }
    )
    return invoice


@transaction.atomic
def post_sales_dispatch(sales_order_id, user, carrier_name='Sri Murugan Roadways', vehicle_number='', lr_number='', notes=''):
    """
    Executes physical and ledger dispatch for a Sales Order:
    1. Validates order status is APPROVED or INVOICED.
    2. Enforces duplicate dispatch protection (is_posted).
    3. Validates finished goods inventory on hand.
    4. Deducts finished goods stock via record_stock_movement (MovementType.SALES_DISPATCH).
    5. Advances order status to DISPATCHED.
    6. Returns Dispatch record with duplicate-posting protection.
    """
    if hasattr(sales_order_id, 'id'):
        sales_order_id = sales_order_id.id
    order = SalesOrder.objects.select_for_update().get(pk=sales_order_id)

    if order.dispatches.filter(is_posted=True).exists() or order.status == SalesOrder.Status.DISPATCHED:
        raise ValidationError(f"Order {order.order_number} has already been dispatched. Duplicate dispatch posting is prohibited.")

    if order.status not in [SalesOrder.Status.APPROVED, SalesOrder.Status.INVOICED]:
        raise ValidationError(f"Cannot dispatch order {order.order_number}: Must be in APPROVED or INVOICED status (currently {order.get_status_display()}).")

    # If not invoiced yet, auto-generate tax invoice first
    if not hasattr(order, 'invoice') or not order.invoice:
        generate_invoice_for_order(order.pk, user)
        order.refresh_from_db()

    # Validate finished goods stock availability
    is_avail, item, on_hand, req = check_order_stock_availability(order)
    if not is_avail:
        shortage = req - on_hand
        raise ValidationError(
            f"Dispatch prohibited! Insufficient stock for {item.item_name}. "
            f"Required: {req} {item.uom.code}, Available on hand: {on_hand} {item.uom.code}, "
            f"Shortage: {shortage} {item.uom.code}. Negative inventory is strictly prohibited."
        )

    dispatch_num = generate_dispatch_number()
    dispatch = Dispatch.objects.create(
        dispatch_number=dispatch_num,
        sales_order=order,
        invoice=order.invoice,
        dispatch_date=date.today(),
        carrier_name=carrier_name or 'Sri Murugan Roadways',
        vehicle_number=vehicle_number,
        lr_number=lr_number,
        status=Dispatch.Status.DISPATCHED,
        is_posted=False,
        dispatched_by=user,
        notes=notes
    )

    # Deduct finished goods stock across line items
    for line in order.items.all():
        qty_needed = line.quantity

        stock_batches = StockItem.objects.filter(
            product_pack_size=line.product_pack_size,
            quantity_on_hand__gt=0
        ).order_by('id')

        for stock in stock_batches:
            if qty_needed <= Decimal('0.00'):
                break

            deduct_qty = min(stock.quantity_on_hand, qty_needed)

            record_stock_movement(
                item_type=ItemType.FINISHED_GOODS,
                movement_type=MovementType.SALES_DISPATCH,
                quantity_change=-deduct_qty,
                uom=line.uom,
                unit_cost=stock.unit_cost,
                reference_type='SALES_DISPATCH',
                reference_id=dispatch.dispatch_number,
                performed_by=user,
                product_pack_size=line.product_pack_size,
                batch_number=stock.batch_number,
                remarks=f"Sales Order {order.order_number} dispatch to {order.customer.name}"
            )
            qty_needed -= deduct_qty

        line.dispatched_quantity = line.quantity
        line.save(update_fields=['dispatched_quantity'])

    # Finalize statuses
    dispatch.is_posted = True
    dispatch.posted_at = timezone.now()
    dispatch.save(update_fields=['is_posted', 'posted_at', 'updated_at'])

    order.status = SalesOrder.Status.DISPATCHED
    order.save(update_fields=['status', 'updated_at'])

    log_audit_event(
        action=AuditLogEntry.Action.DISPATCH_RECORDED,
        module=AuditLogEntry.Module.SALES,
        object_repr=f"Dispatch {dispatch.dispatch_number}",
        object_id=str(dispatch.pk),
        reference_number=dispatch.dispatch_number,
        user=user,
        details={
            'sales_order': order.order_number,
            'invoice_number': order.invoice.invoice_number if order.invoice else None,
            'customer': order.customer.name,
            'carrier_name': dispatch.carrier_name,
            'vehicle_number': dispatch.vehicle_number,
            'lr_number': dispatch.lr_number
        }
    )

    return dispatch


@transaction.atomic
def record_invoice_payment(
    invoice_id=None,
    amount=None,
    payment_mode=PaymentRecord.Mode.NEFT_RTGS,
    reference_no='',
    user=None,
    notes='',
    invoice=None,
    transaction_reference=None,
    recorded_by=None
):
    """
    Records a payment received against an Invoice and updates payment status.
    Supports either invoice_id or invoice object, reference_no or transaction_reference,
    user or recorded_by for full API consistency.
    """
    target = invoice if invoice is not None else invoice_id
    if hasattr(target, 'id'):
        target_id = target.id
    else:
        target_id = target

    ref = transaction_reference if transaction_reference is not None else reference_no
    operator = recorded_by if recorded_by is not None else user

    amount = Decimal(str(amount))
    if amount <= Decimal('0.00'):
        raise ValidationError("Payment amount must be strictly greater than zero.")

    invoice_obj = Invoice.objects.select_for_update().get(pk=target_id)

    if invoice_obj.balance_due <= Decimal('0.00') or invoice_obj.payment_status == Invoice.PaymentStatus.PAID:
        raise ValidationError(f"Invoice {invoice_obj.invoice_number} is already fully settled (PAID). No further payments can be accepted.")

    if amount > invoice_obj.balance_due:
        raise ValidationError(
            f"Payment amount of ₹{amount:.2f} exceeds invoice outstanding balance (₹{invoice_obj.balance_due:.2f}) for invoice {invoice_obj.invoice_number}. "
            f"Overpayment is prohibited."
        )

    pay_num = generate_payment_number()
    payment = PaymentRecord.objects.create(
        payment_number=pay_num,
        invoice=invoice_obj,
        customer=invoice_obj.customer,
        payment_date=date.today(),
        amount=amount,
        payment_mode=payment_mode,
        transaction_reference=ref or '',
        notes=notes or '',
        recorded_by=operator
    )

    invoice_obj.update_payment_status()

    log_audit_event(
        action=AuditLogEntry.Action.PAYMENT_RECORDED,
        module=AuditLogEntry.Module.FINANCE,
        object_repr=f"Payment {payment.payment_number} for Invoice {invoice_obj.invoice_number}",
        object_id=str(payment.pk),
        reference_number=payment.payment_number,
        user=operator,
        details={
            'invoice_number': invoice_obj.invoice_number,
            'customer': invoice_obj.customer.name,
            'amount': payment.amount,
            'payment_mode': payment.payment_mode,
            'reference_no': payment.transaction_reference,
            'balance_due': invoice_obj.balance_due,
            'payment_status': invoice_obj.payment_status
        }
    )

    return payment
