"""
Pure-Python PDF 1.4 Tax Invoice Generator.
Generates fully compliant, downloadable PDF 1.4 documents with zero external C-dependencies.
Follows standard ISO 32000-1 / Adobe PDF specifications with Helvetica Type 1 font.
"""

from decimal import Decimal
from datetime import date
import io


class SimplePDFCanvas:
    """
    Lightweight, deterministic PDF 1.4 stream writer.
    Page geometry: A4 (595.28 x 841.89 pt).
    Coordinate system: Origin (0,0) at bottom-left corner.
    """
    PAGE_WIDTH = 595.28
    PAGE_HEIGHT = 841.89

    def __init__(self):
        self.stream_commands = []

    def set_fill_color(self, r, g, b):
        self.stream_commands.append(f"{r:.3f} {g:.3f} {b:.3f} rg")

    def set_stroke_color(self, r, g, b):
        self.stream_commands.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def set_line_width(self, width):
        self.stream_commands.append(f"{width:.2f} w")

    def draw_line(self, x1, y1, x2, y2, color=(0.7, 0.7, 0.7), width=0.8):
        self.set_stroke_color(*color)
        self.set_line_width(width)
        self.stream_commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def draw_rect(self, x, y, w, h, fill_color=None, stroke_color=None, stroke_width=0.8):
        self.stream_commands.append("q")
        if fill_color is not None:
            self.set_fill_color(*fill_color)
            if stroke_color is not None:
                self.set_stroke_color(*stroke_color)
                self.set_line_width(stroke_width)
                self.stream_commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re B")
            else:
                self.stream_commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
        elif stroke_color is not None:
            self.set_stroke_color(*stroke_color)
            self.set_line_width(stroke_width)
            self.stream_commands.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")
        self.stream_commands.append("Q")

    @staticmethod
    def _escape_pdf_text(text):
        if not text:
            return ""
        # Standard ASCII transliteration for non-ascii characters
        cleaned = str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        # Replace non-ascii chars safely
        safe_chars = []
        for ch in cleaned:
            if ord(ch) < 128:
                safe_chars.append(ch)
            else:
                safe_chars.append('?')
        return "".join(safe_chars)

    def draw_text(self, text, x, y, font='F1', size=10, color=(0.1, 0.1, 0.1)):
        escaped = self._escape_pdf_text(text)
        self.stream_commands.append("BT")
        self.stream_commands.append(f"/{font} {size:.1f} Tf")
        self.set_fill_color(*color)
        self.stream_commands.append(f"{x:.2f} {y:.2f} Td")
        self.stream_commands.append(f"({escaped}) Tj")
        self.stream_commands.append("ET")

    def draw_text_right(self, text, x_right, y, font='F1', size=10, color=(0.1, 0.1, 0.1), approx_char_width=None):
        """Right-aligned text based on approximate font character metrics."""
        escaped = self._escape_pdf_text(text)
        char_w = approx_char_width if approx_char_width else (size * 0.52 if font == 'F1' else size * 0.58)
        text_width = len(escaped) * char_w
        x = max(20.0, x_right - text_width)
        self.draw_text(text, x, y, font=font, size=size, color=color)

    def render_pdf_bytes(self):
        content_stream = "\n".join(self.stream_commands).encode('latin-1', 'replace')
        content_len = len(content_stream)

        # 1: Catalog, 2: Pages, 3: Page, 4: Font F1 (Helvetica), 5: Font F2 (Helvetica-Bold), 6: Stream
        objects = []
        objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        objects.append(
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.28 841.89] "
            b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n"
        )
        objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
        objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")
        objects.append(
            f"6 0 obj\n<< /Length {content_len} >>\nstream\n".encode('latin-1') +
            content_stream +
            b"\nendstream\nendobj\n"
        )

        output = io.BytesIO()
        output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

        offsets = []
        curr_offset = output.tell()
        for obj in objects:
            offsets.append(curr_offset)
            output.write(obj)
            curr_offset = output.tell()

        xref_pos = curr_offset
        num_objects = len(objects) + 1
        output.write(f"xref\n0 {num_objects}\n".encode('latin-1'))
        output.write(b"0000000000 65535 f \n")
        for off in offsets:
            output.write(f"{off:010d} 00000 n \n".encode('latin-1'))

        trailer = (
            f"trailer\n<< /Size {num_objects} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n"
        )
        output.write(trailer.encode('latin-1'))
        return output.getvalue()


def generate_invoice_pdf(invoice):
    """
    Constructs an official, audit-grade GST Tax Invoice PDF for the given Invoice record.
    Returns: binary bytes (application/pdf).
    """
    canvas = SimplePDFCanvas()
    so = invoice.sales_order
    customer = invoice.customer

    # Page Margins & Geometry
    left = 36.0
    right = 559.28
    width = right - left
    top_y = 805.0

    # 1. Top Header Banner
    canvas.draw_rect(left, top_y - 48, width, 48, fill_color=(0.10, 0.22, 0.40))
    canvas.draw_text("MANUFLOW MANUFACTURING & ORDER MANAGEMENT", left + 14, top_y - 18, font='F2', size=13, color=(1, 1, 1))
    canvas.draw_text("ENTERPRISE MANUFACTURING & ORDER-TO-AUDIT SUITE", left + 14, top_y - 32, font='F1', size=8.5, color=(0.85, 0.90, 0.98))
    canvas.draw_text_right("TAX INVOICE (DEMO)", right - 14, top_y - 20, font='F2', size=12, color=(1, 0.85, 0.2))
    canvas.draw_text_right("[ACADEMIC SIMULATION DOCUMENT]", right - 14, top_y - 34, font='F1', size=7.5, color=(0.85, 0.90, 0.98))

    curr_y = top_y - 56

    # 2. Institutional & Invoice Meta Details (2 Columns)
    col_w = (width - 10) / 2
    canvas.draw_rect(left, curr_y - 82, col_w, 82, fill_color=(0.97, 0.98, 1.0), stroke_color=(0.82, 0.86, 0.92))
    canvas.draw_rect(left + col_w + 10, curr_y - 82, col_w, 82, fill_color=(0.97, 0.98, 1.0), stroke_color=(0.82, 0.86, 0.92))

    # Supplier Details (Left)
    canvas.draw_text("SUPPLIER / CONSIGNOR DETAILS", left + 8, curr_y - 14, font='F2', size=8.5, color=(0.10, 0.22, 0.40))
    canvas.draw_text(invoice.company_name, left + 8, curr_y - 27, font='F2', size=9, color=(0.15, 0.15, 0.15))
    canvas.draw_text("Campus, Thuvakudi, Tiruchirappalli - 620015", left + 8, curr_y - 39, font='F1', size=8, color=(0.3, 0.3, 0.3))
    canvas.draw_text(f"GSTIN: {invoice.company_gstin} | State: {invoice.company_state} ({invoice.company_state_code})", left + 8, curr_y - 51, font='F2', size=7.5, color=(0.10, 0.22, 0.40))
    canvas.draw_text("Email: foodtech@nit.edu | Phone: +91 431 2503000", left + 8, curr_y - 63, font='F1', size=8, color=(0.3, 0.3, 0.3))

    # Invoice Details (Right)
    rx = left + col_w + 18
    canvas.draw_text("INVOICE & COMMERCIAL DETAILS", rx, curr_y - 14, font='F2', size=8.5, color=(0.10, 0.22, 0.40))
    canvas.draw_text(f"Invoice Number: {invoice.invoice_number}", rx, curr_y - 27, font='F2', size=9, color=(0.15, 0.15, 0.15))
    canvas.draw_text(f"Invoice Date: {invoice.invoice_date.strftime('%d-%b-%Y')}  |  Due Date: {invoice.due_date.strftime('%d-%b-%Y') if invoice.due_date else 'Immediate'}", rx, curr_y - 39, font='F1', size=8, color=(0.3, 0.3, 0.3))
    canvas.draw_text(f"Sales Order Ref: {so.order_number} ({so.order_date.strftime('%d-%b-%Y')})", rx, curr_y - 51, font='F1', size=8, color=(0.3, 0.3, 0.3))
    supply_type = "Inter-State (IGST 5%)" if invoice.is_interstate else "Intra-State (CGST 2.5% + SGST 2.5%)"
    canvas.draw_text(f"Place of Supply: {invoice.place_of_supply}  [{supply_type}]", rx, curr_y - 63, font='F2', size=8, color=(0.10, 0.22, 0.40))

    curr_y -= 90

    # 3. Buyer / Consignee Details (2 Columns: Billing Address & Shipping Address)
    canvas.draw_rect(left, curr_y - 72, col_w, 72, fill_color=(0.99, 0.99, 0.99), stroke_color=(0.82, 0.86, 0.92))
    canvas.draw_rect(left + col_w + 10, curr_y - 72, col_w, 72, fill_color=(0.99, 0.99, 0.99), stroke_color=(0.82, 0.86, 0.92))

    canvas.draw_text("BILLED TO (BUYER DETAILS)", left + 8, curr_y - 14, font='F2', size=8.5, color=(0.10, 0.22, 0.40))
    canvas.draw_text(f"{invoice.customer_name} ({customer.get_customer_type_display()})", left + 8, curr_y - 27, font='F2', size=9, color=(0.15, 0.15, 0.15))
    b_addr = (invoice.billing_address or customer.billing_address or 'Customer Registered Address').replace('\n', ', ')[:52]
    canvas.draw_text(b_addr, left + 8, curr_y - 39, font='F1', size=8, color=(0.3, 0.3, 0.3))
    canvas.draw_text(f"GSTIN / Tax ID: {invoice.customer_gstin or 'UNREGISTERED'} | State: {customer.state}", left + 8, curr_y - 51, font='F1', size=8, color=(0.3, 0.3, 0.3))

    canvas.draw_text("SHIPPED / DELIVERED TO", rx, curr_y - 14, font='F2', size=8.5, color=(0.10, 0.22, 0.40))
    canvas.draw_text(f"{invoice.customer_name}", rx, curr_y - 27, font='F2', size=9, color=(0.15, 0.15, 0.15))
    s_addr = (invoice.shipping_address or so.delivery_address or customer.shipping_address or 'Same as Billing').replace('\n', ', ')[:52]
    canvas.draw_text(s_addr, rx, curr_y - 39, font='F1', size=8, color=(0.3, 0.3, 0.3))
    canvas.draw_text(f"Destination: {so.delivery_city or customer.city}, {so.delivery_state or customer.state}", rx, curr_y - 51, font='F1', size=8, color=(0.3, 0.3, 0.3))

    curr_y -= 80

    # 4. Itemized Product Table Header
    # Columns: # (24), Description (150), HSN (50), Qty (45), Rate (45), Taxable (55), CGST (45), SGST (45), IGST (45), Total (50) -> total = 554
    th_h = 20
    canvas.draw_rect(left, curr_y - th_h, width, th_h, fill_color=(0.14, 0.26, 0.44))

    canvas.draw_text("#", left + 4, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    canvas.draw_text("Description of Goods", left + 22, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    canvas.draw_text("HSN/SAC", left + 185, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    canvas.draw_text_right("Qty", left + 265, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    canvas.draw_text_right("Rate (INR)", left + 325, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    canvas.draw_text_right("Taxable", left + 380, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    if invoice.is_interstate:
        canvas.draw_text_right("IGST (5%)", left + 450, curr_y - 14, font='F2', size=8, color=(1, 1, 1))
    else:
        canvas.draw_text_right("CGST (2.5%)", left + 435, curr_y - 14, font='F2', size=7.5, color=(1, 1, 1))
        canvas.draw_text_right("SGST (2.5%)", left + 480, curr_y - 14, font='F2', size=7.5, color=(1, 1, 1))
    canvas.draw_text_right("Total (INR)", right - 6, curr_y - 14, font='F2', size=8, color=(1, 1, 1))

    curr_y -= th_h

    # 5. Table Rows
    items = list(so.items.all())
    row_h = 24
    row_count = 0

    for idx, item in enumerate(items, start=1):
        bg = (0.98, 0.98, 0.99) if row_count % 2 == 1 else (1.0, 1.0, 1.0)
        canvas.draw_rect(left, curr_y - row_h, width, row_h, fill_color=bg, stroke_color=(0.88, 0.90, 0.94))

        sku_desc = f"{item.product_pack_size.product.name} - {item.product_pack_size.pack_name}"
        hsn = getattr(item.product_pack_size.product, 'hsn_code', None) or "19059040"
        qty_str = f"{item.quantity:.0f} {item.uom.code}"
        rate_str = f"{item.unit_price:.2f}"
        taxable_str = f"{item.subtotal:.2f}"

        canvas.draw_text(str(idx), left + 6, curr_y - 15, font='F1', size=8)
        canvas.draw_text(sku_desc[:32], left + 22, curr_y - 15, font='F2', size=8.5)
        canvas.draw_text(hsn, left + 185, curr_y - 15, font='F1', size=8)
        canvas.draw_text_right(qty_str, left + 265, curr_y - 15, font='F1', size=8)
        canvas.draw_text_right(rate_str, left + 325, curr_y - 15, font='F1', size=8)
        canvas.draw_text_right(taxable_str, left + 380, curr_y - 15, font='F1', size=8)

        if invoice.is_interstate:
            canvas.draw_text_right(f"{item.igst_amount:.2f}", left + 450, curr_y - 15, font='F1', size=8)
        else:
            canvas.draw_text_right(f"{item.cgst_amount:.2f}", left + 435, curr_y - 15, font='F1', size=8)
            canvas.draw_text_right(f"{item.sgst_amount:.2f}", left + 480, curr_y - 15, font='F1', size=8)

        canvas.draw_text_right(f"{item.total_price:.2f}", right - 6, curr_y - 15, font='F2', size=8.5)

        curr_y -= row_h
        row_count += 1

    curr_y -= 12

    # 6. Commercial Financial Summary Block
    sum_w = 230.0
    sum_x = right - sum_w
    canvas.draw_rect(sum_x, curr_y - 110, sum_w, 110, fill_color=(0.97, 0.98, 1.0), stroke_color=(0.82, 0.86, 0.92))

    canvas.draw_text("Taxable Subtotal:", sum_x + 10, curr_y - 18, font='F1', size=8.5)
    canvas.draw_text_right(f"INR {invoice.taxable_amount:.2f}", right - 12, curr_y - 18, font='F2', size=9)

    if invoice.is_interstate:
        canvas.draw_text(f"Integrated GST (IGST @ {invoice.igst_rate_pct:.1f}%):", sum_x + 10, curr_y - 34, font='F1', size=8.5)
        canvas.draw_text_right(f"INR {invoice.igst_amount:.2f}", right - 12, curr_y - 34, font='F1', size=8.5)
    else:
        canvas.draw_text(f"Central GST (CGST @ {invoice.cgst_rate_pct:.1f}%):", sum_x + 10, curr_y - 32, font='F1', size=8)
        canvas.draw_text_right(f"INR {invoice.cgst_amount:.2f}", right - 12, curr_y - 32, font='F1', size=8)
        canvas.draw_text(f"State GST (SGST @ {invoice.sgst_rate_pct:.1f}%):", sum_x + 10, curr_y - 46, font='F1', size=8)
        canvas.draw_text_right(f"INR {invoice.sgst_amount:.2f}", right - 12, curr_y - 46, font='F1', size=8)

    canvas.draw_line(sum_x + 8, curr_y - 56, right - 8, curr_y - 56, color=(0.75, 0.80, 0.88), width=0.8)

    canvas.draw_text("Total Tax Amount:", sum_x + 10, curr_y - 68, font='F1', size=8.5)
    canvas.draw_text_right(f"INR {invoice.total_tax:.2f}", right - 12, curr_y - 68, font='F1', size=8.5)

    canvas.draw_rect(sum_x + 4, curr_y - 105, sum_w - 8, 28, fill_color=(0.10, 0.22, 0.40))
    canvas.draw_text("GRAND TOTAL (INCL. GST):", sum_x + 12, curr_y - 88, font='F2', size=9, color=(1, 1, 1))
    canvas.draw_text_right(f"INR {invoice.grand_total:.2f}", right - 12, curr_y - 88, font='F2', size=11, color=(1, 0.88, 0.2))

    # Payment Status Box (Left of Summary)
    pay_w = width - sum_w - 15
    canvas.draw_rect(left, curr_y - 110, pay_w, 110, fill_color=(0.99, 0.99, 0.99), stroke_color=(0.82, 0.86, 0.92))
    canvas.draw_text("SETTLEMENT & PAYMENT DETAILS", left + 10, curr_y - 18, font='F2', size=8.5, color=(0.10, 0.22, 0.40))

    status_color = (0.1, 0.6, 0.2) if invoice.payment_status == 'PAID' else (0.8, 0.4, 0.0)
    canvas.draw_text(f"Payment Status: {invoice.get_payment_status_display().upper()}", left + 10, curr_y - 34, font='F2', size=9, color=status_color)
    canvas.draw_text(f"Total Amount Received: INR {invoice.amount_paid:.2f}", left + 10, curr_y - 48, font='F1', size=8.5)
    canvas.draw_text(f"Outstanding Balance: INR {invoice.balance_due:.2f}", left + 10, curr_y - 62, font='F2', size=9, color=(0.8, 0.1, 0.1) if invoice.balance_due > 0 else (0.1, 0.5, 0.1))
    canvas.draw_text("Bank Name: State Bank of India, NIT Trichy Branch", left + 10, curr_y - 78, font='F1', size=8, color=(0.3, 0.3, 0.3))
    canvas.draw_text("Account No: 100987654321 | IFSC: SBIN0001617", left + 10, curr_y - 92, font='F1', size=8, color=(0.3, 0.3, 0.3))

    curr_y -= 130

    # 7. Terms & Declarations / Signatory
    canvas.draw_rect(left, curr_y - 70, width, 70, fill_color=(0.98, 0.98, 0.99), stroke_color=(0.85, 0.88, 0.92))
    canvas.draw_text("TERMS & CONDITIONS", left + 10, curr_y - 14, font='F2', size=8, color=(0.2, 0.2, 0.2))
    canvas.draw_text("1. Goods once sold will not be taken back or exchanged after dispatch.", left + 10, curr_y - 26, font='F1', size=7.5, color=(0.4, 0.4, 0.4))
    canvas.draw_text("2. Interest @ 18% p.a. will be levied if payment is not cleared by due date.", left + 10, curr_y - 37, font='F1', size=7.5, color=(0.4, 0.4, 0.4))
    canvas.draw_text("3. Subject to Tiruchirappalli jurisdiction only. Certified that particulars given above are true and correct.", left + 10, curr_y - 48, font='F1', size=7.5, color=(0.4, 0.4, 0.4))

    # Signature Block
    sig_x = right - 160
    canvas.draw_text("For ManuFlow Operations & Manufacturing", sig_x - 10, curr_y - 20, font='F2', size=7.5, color=(0.10, 0.22, 0.40))
    canvas.draw_line(sig_x, curr_y - 46, right - 15, curr_y - 46, color=(0.5, 0.5, 0.5), width=0.8)
    canvas.draw_text("Authorised Signatory", sig_x + 15, curr_y - 56, font='F1', size=7.5, color=(0.3, 0.3, 0.3))

    # Bottom watermark/footer
    canvas.draw_text("NOTICE: Academic simulation document for ManuFlow training & evaluation. Not a certified GST Tax Invoice for commercial statutory filing.", left, 25.0, font='F1', size=6.8, color=(0.4, 0.4, 0.4))
    canvas.draw_text_right("Page 1 of 1", right, 25.0, font='F1', size=7, color=(0.5, 0.5, 0.5))

    return canvas.render_pdf_bytes()
