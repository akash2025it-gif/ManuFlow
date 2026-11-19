from decimal import Decimal
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Avg, Count, Q
from django.http import HttpResponseForbidden

from apps.accounts.decorators import role_required
from apps.accounts.models import CustomUser
from apps.inventory.models import StockLedgerEntry
from .models import ProductionRun, ProductionMaterialConsumption
from .forms import (
    ProductionRunCreateForm,
    ProductionRunExecuteForm,
    ProductionMaterialConsumptionFormSet,
)
from .services import create_production_run_from_bom, post_production_run


@login_required
def production_dashboard_view(request):
    """
    Central Executive & Shop Floor Production Management Dashboard.
    Provides KPIs, run status breakdown, active yield variance alerts, and recent runs.
    """
    total_runs = ProductionRun.objects.count()
    completed_runs = ProductionRun.objects.filter(status=ProductionRun.Status.COMPLETED).count()
    in_progress_runs = ProductionRun.objects.filter(status=ProductionRun.Status.IN_PROGRESS).count()
    draft_runs = ProductionRun.objects.filter(status=ProductionRun.Status.DRAFT).count()

    total_units_produced = ProductionRun.objects.filter(
        status=ProductionRun.Status.COMPLETED
    ).aggregate(total=Sum('actual_output_quantity'))['total'] or Decimal('0.00')

    # Query completed runs to evaluate yield performance and alerts
    completed_runs_qs = ProductionRun.objects.filter(status=ProductionRun.Status.COMPLETED)
    alert_count = sum(1 for r in completed_runs_qs if r.has_any_variance_alert)

    recent_runs = ProductionRun.objects.select_related(
        'product', 'product_pack_size', 'bill_of_materials'
    ).order_by('-created_at')[:8]

    context = {
        'total_runs': total_runs,
        'completed_runs': completed_runs,
        'in_progress_runs': in_progress_runs,
        'draft_runs': draft_runs,
        'total_units_produced': total_units_produced,
        'alert_count': alert_count,
        'recent_runs': recent_runs,
    }
    return render(request, 'production/dashboard.html', context)


@login_required
def production_run_list_view(request):
    """
    Filterable list of all Production Runs / Work Orders.
    Supports filtering by status, product, date, and variance alerts (> 3%).
    """
    qs = ProductionRun.objects.select_related(
        'product', 'product_pack_size', 'bill_of_materials', 'created_by'
    ).order_by('-created_at')

    # Search query
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(run_number__icontains=q) |
            Q(batch_number__icontains=q) |
            Q(product__name__icontains=q) |
            Q(product_pack_size__pack_name__icontains=q)
        )

    # Status filter
    status = request.GET.get('status', '').strip()
    if status:
        qs = qs.filter(status=status)

    # Variance alert filter
    alert_filter = request.GET.get('alert', '').strip()
    if alert_filter == '1':
        # Filter for runs with any variance alert
        alert_ids = [r.id for r in qs if r.has_any_variance_alert]
        qs = qs.filter(id__in=alert_ids)

    paginator = Paginator(qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status,
        'alert_filter': alert_filter,
        'status_choices': ProductionRun.Status.choices,
    }
    return render(request, 'production/run_list.html', context)


@login_required
def production_run_create_view(request):
    """
    Create a new Production Run / Work Order from an active BOM.
    Restricted to PRODUCTION and ADMIN roles.
    """
    if request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.PRODUCTION] and not request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: Only Production supervisors and Admins can create production runs.")

    if request.method == 'POST':
        form = ProductionRunCreateForm(request.POST)
        if form.is_valid():
            try:
                run = create_production_run_from_bom(
                    bom=form.cleaned_data['bill_of_materials'],
                    planned_quantity=form.cleaned_data['planned_quantity'],
                    user=request.user,
                    product_pack_size=form.cleaned_data.get('product_pack_size'),
                    batch_number=form.cleaned_data.get('batch_number', ''),
                    manufacture_date=form.cleaned_data.get('manufacture_date'),
                    expiry_date=form.cleaned_data.get('expiry_date'),
                    variance_alert_threshold_pct=form.cleaned_data.get('variance_alert_threshold_pct', Decimal('3.00')),
                    notes=form.cleaned_data.get('notes', '')
                )
                messages.success(
                    request,
                    f"Production Run {run.run_number} created successfully with planned requirements for "
                    f"{run.planned_quantity} {run.product_pack_size.pack_name}."
                )
                return redirect('production_run_detail', pk=run.pk)
            except ValidationError as e:
                form.add_error(None, e)
    else:
        form = ProductionRunCreateForm()

    context = {
        'form': form,
        'title': 'Create New Production Run',
    }
    return render(request, 'production/run_create.html', context)


@login_required
def production_run_detail_view(request, pk):
    """
    Comprehensive Work Order Detail:
    - BOM recipe & expected vs actual output yield
    - Ingredient consumption with planned vs actual variance and alert badges
    - Direct Labour & Gas/Power overhead cost breakdown
    - Weighted-average total production costing and unit output cost
    - Traceable stock movements logged in StockLedgerEntry
    """
    run = get_object_or_404(
        ProductionRun.objects.select_related(
            'product', 'product_pack_size', 'bill_of_materials', 'created_by', 'posted_by'
        ),
        pk=pk
    )

    materials = run.materials.select_related(
        'raw_material', 'packaging_material', 'uom'
    ).order_by('item_type', 'id')

    # Linked stock movements
    ledger_entries = StockLedgerEntry.objects.filter(
        reference_type='PRODUCTION_RUN',
        reference_id=run.run_number
    ).select_related('raw_material', 'packaging_material', 'product_pack_size', 'uom', 'performed_by').order_by('id')

    context = {
        'run': run,
        'materials': materials,
        'ledger_entries': ledger_entries,
    }
    return render(request, 'production/run_detail.html', context)


@login_required
def production_run_execute_view(request, pk):
    """
    Floor execution interface to record actual good output, damaged packaging,
    actual material consumption, and allocated overheads (Labour, Gas/Power).
    Restricted to PRODUCTION and ADMIN roles.
    """
    if request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.PRODUCTION] and not request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: Only Production supervisors and Admins can record execution.")

    run = get_object_or_404(ProductionRun, pk=pk)

    if run.is_posted:
        messages.warning(request, f"Production Run {run.run_number} has already been completed and posted.")
        return redirect('production_run_detail', pk=run.pk)

    if request.method == 'POST':
        form = ProductionRunExecuteForm(request.POST, instance=run)
        formset = ProductionMaterialConsumptionFormSet(request.POST, instance=run)

        if form.is_valid() and formset.is_valid():
            run_obj = form.save(commit=False)
            if run_obj.status == ProductionRun.Status.DRAFT:
                run_obj.status = ProductionRun.Status.IN_PROGRESS
            run_obj.save()
            formset.save()

            messages.success(request, f"Execution measurements updated for {run.run_number}.")

            # If user clicked "Save and Post to Inventory"
            if 'post_to_inventory' in request.POST:
                try:
                    post_production_run(run.pk, request.user)
                    messages.success(
                        request,
                        f"Production Run {run.run_number} successfully posted to inventory ledger! "
                        f"Finished output {run.actual_output_quantity} units added; materials deducted."
                    )
                    return redirect('production_run_detail', pk=run.pk)
                except ValidationError as e:
                    messages.error(request, f"Inventory posting failed: {e}")

            return redirect('production_run_detail', pk=run.pk)
    else:
        # Initial defaults if empty
        if run.actual_output_quantity == Decimal('0.00'):
            run.actual_output_quantity = run.expected_output_quantity
        form = ProductionRunExecuteForm(instance=run)
        formset = ProductionMaterialConsumptionFormSet(instance=run)

    context = {
        'run': run,
        'form': form,
        'formset': formset,
    }
    return render(request, 'production/run_execute.html', context)


@login_required
def production_run_post_view(request, pk):
    """
    Direct POST action to complete a production run and post to stock ledger.
    """
    if request.user.role not in [CustomUser.Role.ADMIN, CustomUser.Role.PRODUCTION] and not request.user.is_superuser:
        return HttpResponseForbidden("Access Denied: Only Production supervisors and Admins can post production runs.")

    if request.method != 'POST':
        return redirect('production_run_detail', pk=pk)

    run = get_object_or_404(ProductionRun, pk=pk)

    try:
        post_production_run(run.pk, request.user)
        messages.success(
            request,
            f"Production Run {run.run_number} successfully posted to inventory ledger! "
            f"Finished goods batch {run.batch_number} (+{run.actual_output_quantity}) received. "
            f"Unit cost: ₹{run.unit_cost_per_output}."
        )
    except ValidationError as e:
        messages.error(request, f"Failed to post production run: {e}")

    return redirect('production_run_detail', pk=pk)


@login_required
def production_reports_view(request):
    """
    Analytical Production & Variance Intelligence Report.
    Auditors, Owners, and Production managers can evaluate:
    - Yield variance history and 3% tolerance threshold breach log
    - Material consumption efficiency (planned vs actual)
    - Overhead cost absorption (Labour, Gas/Power)
    - Batch cost trends
    """
    completed_runs = ProductionRun.objects.filter(
        status=ProductionRun.Status.COMPLETED
    ).select_related('product', 'product_pack_size', 'bill_of_materials').order_by('-completed_at' if hasattr(ProductionRun, 'completed_at') else '-created_at')

    # Aggregated metrics
    total_completed = completed_runs.count()
    total_output = sum(r.actual_output_quantity for r in completed_runs)
    total_material_cost = sum(r.total_material_cost for r in completed_runs)
    total_overhead_cost = sum(r.total_overhead_cost for r in completed_runs)
    total_production_cost = sum(r.total_production_cost for r in completed_runs)

    # Runs with variance alerts
    alert_runs = [r for r in completed_runs if r.has_any_variance_alert]

    # Material variance log
    material_alerts = ProductionMaterialConsumption.objects.filter(
        production_run__status=ProductionRun.Status.COMPLETED
    ).select_related('production_run', 'raw_material', 'packaging_material', 'uom')

    material_alert_lines = [m for m in material_alerts if m.is_variance_alert_triggered]

    context = {
        'total_completed': total_completed,
        'total_output': total_output,
        'total_material_cost': total_material_cost,
        'total_overhead_cost': total_overhead_cost,
        'total_production_cost': total_production_cost,
        'alert_runs': alert_runs,
        'material_alert_lines': material_alert_lines,
        'completed_runs': completed_runs[:20],
    }
    return render(request, 'production/reports.html', context)
