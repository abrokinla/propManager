import io
import re
import logging
from datetime import date
from urllib.request import urlopen
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image, ListFlowable, ListItem
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)


def _html_to_elements(html: str, style, item_number_start: int = 1) -> list:
    """Convert HTML with <ol>/<li> into ReportLab flowables."""
    if not html:
        return []
    result = []
    # Extract text before any <ol>
    before = re.split(r'<ol>', html, maxsplit=1)[0]
    if before.strip():
        clean = re.sub(r'<[^>]+>', '', before).strip()
        if clean:
            result.append(Paragraph(clean, style))
            result.append(Spacer(1, 2))
    # Find list items
    items = re.findall(r'<li>(.*?)</li>', html, re.DOTALL)
    for i, item_text in enumerate(items):
        clean = re.sub(r'<[^>]+>', '', item_text).strip()
        if clean:
            num = item_number_start + i
            result.append(Paragraph(f"<b>{num}.</b>  {clean}", style))
            result.append(Spacer(1, 1))
    # Extract text after </ol>
    after = re.split(r'</ol>', html, maxsplit=1)
    if len(after) > 1 and after[1].strip():
        clean = re.sub(r'<[^>]+>', '', after[1]).strip()
        if clean:
            result.append(Spacer(1, 2))
            result.append(Paragraph(clean, style))
    return result


def _fmt_date(d):
    if not d:
        return ''
    day = d.day
    suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return f"{day}{suffix} {d.strftime('%B, %Y')}"


def generate_tenancy_agreement(document_data: dict, signature_name: str = None, signed_date: date = None, logo_url: str = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('DocTitle', parent=styles['Title'], fontSize=18, spaceAfter=6, textColor=HexColor('#1a1a2e'), alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('DocSubtitle', fontSize=10, leading=14, spaceAfter=4, textColor=HexColor('#555555'), alignment=TA_CENTER)
    heading_style = ParagraphStyle('DocHeading', fontSize=13, spaceAfter=8, spaceBefore=14, textColor=HexColor('#16213e'), fontName='Helvetica-Bold')
    normal = ParagraphStyle('DocNormal', fontSize=10, leading=15, spaceAfter=4, spaceBefore=0)
    bold = ParagraphStyle('DocBold', parent=normal, fontName='Helvetica-Bold')
    legal_note = ParagraphStyle('LegalNote', fontSize=9, leading=12, spaceAfter=4, textColor=HexColor('#555555'), fontName='Helvetica-Oblique')
    small = ParagraphStyle('DocSmall', fontSize=8.5, leading=11, textColor=HexColor('#555555'))
    clause_style = ParagraphStyle('Clause', fontSize=10, leading=14, spaceAfter=3, spaceBefore=0, leftIndent=12)
    signature_style = ParagraphStyle('Signature', fontSize=11, leading=16, spaceAfter=2, textColor=HexColor('#1a1a2e'))

    elements = []

    # ── Logo ──
    if logo_url:
        try:
            img_data = urlopen(logo_url, timeout=10).read()
            img = Image(io.BytesIO(img_data), width=3.5*cm, height=3.5*cm)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 6))
        except Exception:
            logger.warning(f"Failed to load logo: {logo_url}")

    # ── Agent / Management Company Header ──
    agent = document_data.get('agent', {}) or {}
    if agent.get('name'):
        elements.append(Paragraph(agent['name'], title_style))
        if agent.get('description'):
            elements.append(Paragraph(agent['description'], subtitle_style))
        addr_parts = []
        if agent.get('address'):
            addr_parts.append(agent['address'])
        if agent.get('mobile'):
            addr_parts.append(f"Tel: {agent['mobile']}")
        if agent.get('email'):
            addr_parts.append(f"Email: {agent['email']}")
        if addr_parts:
            elements.append(Paragraph('<br/>'.join(addr_parts), subtitle_style))
        elements.append(Spacer(1, 4))

    # ── Title ──
    elements.append(Spacer(1, 6))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=HexColor('#0f3460'), spaceAfter=4))
    elements.append(Paragraph("TENANCY AGREEMENT", ParagraphStyle('MainTitle', parent=title_style, fontSize=20, spaceAfter=2)))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=HexColor('#0f3460'), spaceAfter=12))

    # ── Date ──
    elements.append(Paragraph(f"<b>Date:</b>  {document_data.get('document_date', '')}", normal))
    elements.append(Spacer(1, 8))

    # ── Parties ──
    elements.append(Paragraph("PARTIES", heading_style))
    landlord = document_data.get('landlord', {}) or {}
    tenant_name = document_data.get('tenant_name', '')
    landlord_name = landlord.get('name', '')
    if landlord_name:
        elements.append(Paragraph(f"<b>{landlord_name}</b> (hereinafter referred to as the \"<b>LANDLORD</b>\") — {landlord.get('legal_note', '')}", normal))
    if landlord.get('address'):
        elements.append(Paragraph(f"Address: {landlord['address']}", normal))
    if tenant_name:
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<b>{tenant_name}</b> (hereinafter referred to as the \"<b>TENANT</b>\") — {document_data.get('tenants_legal_note', '')}", normal))
    elements.append(Spacer(1, 6))

    # ── Property ──
    prop = document_data.get('property', {}) or {}
    elements.append(Paragraph("THE DEMISED PREMISES", heading_style))
    referred = prop.get('referred_to_as', 'the demised premises')
    if prop.get('description'):
        elements.append(Paragraph(f"<b>Description:</b>  {prop['description']}", normal))
    if prop.get('address'):
        elements.append(Paragraph(f"<b>Address:</b>  {prop['address']}", normal))
    if prop.get('unit_number'):
        elements.append(Paragraph(f"<b>Unit:</b>  {prop['unit_number']}", normal))
    if prop.get('ownership_note'):
        elements.append(Paragraph(f"<i>{prop['ownership_note']}</i>", legal_note))
    elements.append(Paragraph(f"(hereinafter referred to as \"<b>{referred}</b>\")", normal))
    elements.append(Spacer(1, 6))

    # ── Tenancy Terms ──
    terms = document_data.get('tenancy_terms', {}) or {}
    elements.append(Paragraph("TENANCY TERMS", heading_style))
    table_data = []
    if terms.get('type'):
        table_data.append(['Type of Tenancy', terms['type']])
    if terms.get('annual_rent_amount'):
        amt = float(terms['annual_rent_amount'])
        table_data.append(['Annual Rent', f"₦{amt:,.2f} ({terms.get('currency', 'NGN')})"])
    if terms.get('annual_rent_in_words'):
        table_data.append(['(in words)', terms['annual_rent_in_words']])
    if terms.get('payment'):
        table_data.append(['Payment Terms', terms['payment']])
    if terms.get('due_by'):
        table_data.append(['Due By', terms['due_by']])
    if terms.get('commencement_date'):
        table_data.append(['Commencement Date', terms['commencement_date']])
    if terms.get('expiry_date'):
        table_data.append(['Expiry Date', terms['expiry_date']])
    if terms.get('duration_years'):
        table_data.append(['Duration', f"{terms['duration_years']} year(s)"])
    if table_data:
        t = Table(table_data, colWidths=[5.5*cm, 10*cm])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.3, HexColor('#cccccc')),
            ('BACKGROUND', (0, 0), (0, -1), HexColor('#f5f5f5')),
        ]))
        elements.append(t)
    elements.append(Spacer(1, 4))

    # ── Caution Fee ──
    caution = terms.get('caution_fee', {}) or {}
    if caution.get('amount'):
        elements.append(Paragraph("Caution Fee", heading_style))
        cf_data = [
            ['Amount', f"₦{float(caution['amount']):,.2f} ({caution.get('currency', 'NGN')})"],
            ['Type', caution.get('type', '')],
        ]
        ct = Table(cf_data, colWidths=[4.5*cm, 11*cm])
        ct.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.3, HexColor('#cccccc')),
            ('BACKGROUND', (0, 0), (0, -1), HexColor('#f5f5f5')),
        ]))
        elements.append(ct)
        elements.append(Spacer(1, 6))

        for field, label in [('deducted_for', 'Deducted For'), ('refunded_if', 'Refunded If'), ('top_up', 'Top Up')]:
            html = caution.get(field, '')
            if html:
                elements.append(Paragraph(f"<b>{label}</b>", normal))
                elements += _html_to_elements(html, clause_style)
                elements.append(Spacer(1, 4))

    # ── Tenant's Covenants ──
    tc_html = document_data.get('tenants_covenants', '')
    if tc_html:
        elements.append(Paragraph("TENANT'S COVENANTS", heading_style))
        elements += _html_to_elements(tc_html, clause_style, item_number_start=1)
        elements.append(Spacer(1, 6))

    # ── Landlord's Covenants ──
    lc_html = document_data.get('landlords_covenants', '')
    if lc_html:
        elements.append(Paragraph("LANDLORD'S COVENANTS", heading_style))
        elements += _html_to_elements(lc_html, clause_style, item_number_start=1)
        elements.append(Spacer(1, 6))

    # ── Special Provisions ──
    sp = document_data.get('special_provisions', {}) or {}
    elements.append(Paragraph("SPECIAL PROVISIONS", heading_style))
    if sp.get('notice_to_quit_months'):
        elements.append(Paragraph(
            f"<b>Notice to Quit:</b>  Where the landlord does not intend to renew, "
            f"the tenant is entitled to <b>{sp['notice_to_quit_months']} months'</b> notice. "
            f"Notice can be issued during or after the tenancy.", normal))
    if sp.get('termination_notice_months'):
        elements.append(Paragraph(
            f"<b>Termination by Either Party:</b>  Either party may terminate by giving "
            f"<b>{sp['termination_notice_months']} months'</b> written notice. "
            f"The tenant is entitled to a refund of unexpired rent after re-letting.", normal))
    if sp.get('holding_over_days'):
        elements.append(Paragraph(
            f"<b>Holding Over:</b>  If the tenant remains after expiration without a new agreement, "
            f"the landlord may issue a <b>{sp['holding_over_days']}-day</b> "
            f"Notice of Owner's Intention to Apply to Court to Recover Possession.", normal))
    if sp.get('communication_methods'):
        elements.append(Paragraph(f"<b>Mode of Communication:</b>  {sp['communication_methods']}", normal))
    if sp.get('renewal_request_months'):
        elements.append(Paragraph(
            f"<b>Renewal:</b>  The tenant must make a written request for renewal at least "
            f"<b>{sp['renewal_request_months']} months</b> before expiry. "
            f"If no request is made, the tenancy is deemed terminated at expiration.", normal))
    if sp.get('rent_review_notice_months'):
        elements.append(Paragraph(
            f"<b>Rent Review:</b>  The landlord reserves the right to review rent by giving "
            f"<b>{sp['rent_review_notice_months']} months'</b> written notice before expiration.", normal))
    if sp.get('rent_review_reply_weeks'):
        elements.append(Paragraph(
            f"<b>Reply to Rent Review:</b>  The tenant must reply in writing within "
            f"<b>{sp['rent_review_reply_weeks']} weeks</b> of receiving a rent review notice. "
            f"Failure to reply means the tenant accepts the reviewed rent. "
            f"If no agreement, the tenant shall vacate upon expiry.", normal))
    extra = sp.get('extra_clauses', '')
    if extra:
        elements.append(Spacer(1, 4))
        elements += _html_to_elements(extra, clause_style)
    elements.append(Spacer(1, 6))

    # ── Execution / Signature ──
    exec_data = document_data.get('execution', {}) or {}
    elements.append(HRFlowable(width="100%", thickness=1, color=HexColor('#0f3460'), spaceAfter=6, spaceBefore=10))
    elements.append(Paragraph("EXECUTION", heading_style))

    if signature_name and signed_date:
        # Signed version — both sides pre-filled
        elements.append(Spacer(1, 8))
        landlord_label = exec_data.get('landlord_label', 'Signed by the within-named LANDLORD')
        tenant_label = exec_data.get('tenant_label', 'Signed by the within-named TENANT')
        landlord_name = (document_data.get('landlord', {}) or {}).get('name', '')
        tenant_witness = document_data.get('witness_tenant', {}) or {}
        sig_table_data = [
            ['', ''],
            [Paragraph(f"<b>{landlord_label}</b>", normal), Paragraph(f"<b>{tenant_label}</b>", normal)],
            ['', ''],
            [Paragraph(f"<b>Name:</b>  {landlord_name}", signature_style), Paragraph(f"<b>Name:</b>  {signature_name}", signature_style)],
            ['', ''],
            [Paragraph(f"<b>Signature:</b>  {landlord_name}", signature_style), Paragraph(f"<b>Signature:</b>  {signature_name} (electronic)", signature_style)],
            ['', ''],
            [Paragraph(f"<b>Date:</b>  {_fmt_date(signed_date)}", signature_style), Paragraph(f"<b>Date:</b>  {_fmt_date(signed_date)}", signature_style)],
            ['', ''],
            ['<b>Witness:</b>', '<b>Witness:</b>'],
            [Paragraph(f"<b>Name:</b>  {exec_data.get('witness_landlord_name', '')}", signature_style), Paragraph(f"<b>Name:</b>  {tenant_witness.get('witness_name', '')}", signature_style)],
            [Paragraph(f"<b>Address:</b>  {exec_data.get('witness_landlord_address', '')}", signature_style), Paragraph(f"<b>Address:</b>  {tenant_witness.get('witness_address', '')}", signature_style)],
            [Paragraph(f"<b>Occupation:</b>  ________________________", signature_style), Paragraph(f"<b>Occupation:</b>  {tenant_witness.get('witness_occupation', '')}", signature_style)],
        ]
        st = Table(sig_table_data, colWidths=[8*cm, 8*cm])
        st.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(st)
    else:
        # Unsigned version — show signature blocks
        elements.append(Spacer(1, 8))
        landlord_label = exec_data.get('landlord_label', 'Signed by the within-named LANDLORD')
        tenant_label = exec_data.get('tenant_label', 'Signed by the within-named TENANT')
        sig_table_data = [
            ['', ''],
            [Paragraph(f"<b>{landlord_label}</b>", normal), Paragraph(f"<b>{tenant_label}</b>", normal)],
            ['', ''],
            ['Name: ..........................', 'Name: ..........................'],
            ['', ''],
            ['Signature: ......................', 'Signature: ......................'],
            ['', ''],
            ['Date: ............................', 'Date: ............................'],
            ['', ''],
            ['<b>Witness:</b>', '<b>Witness:</b>'],
            ['Name: ..........................', 'Name: ..........................'],
            ['Address: .......................', 'Address: .......................'],
            ['Occupation: ..................', 'Occupation: ..................'],
            ['Signature: ......................', 'Signature: ......................'],
        ]
        st = Table(sig_table_data, colWidths=[8*cm, 8*cm])
        st.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(st)

    # ── Footer ──
    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=6))
    elements.append(Paragraph(f"Generated on {_fmt_date(date.today())} via PropManager", small))
    elements.append(Paragraph("This document is computer-generated and does not require a physical signature.", small))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def generate_quit_notice(tenant_name: str, unit_number: str, property_name: str,
                         notice_date: date, effective_date: date, reason: str = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, spaceAfter=20, textColor=HexColor('#8b0000'))
    normal = ParagraphStyle('Normal2', parent=styles['Normal'], fontSize=11, leading=16, spaceAfter=8)
    small = ParagraphStyle('Small2', parent=normal, fontSize=9, textColor=HexColor('#555555'))

    elements = []
    elements.append(Paragraph("QUIT NOTICE", title_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=HexColor('#8b0000'), spaceAfter=16))
    elements.append(Paragraph(f"Date: {notice_date.strftime('%B %d, %Y')}", normal))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(f"To: {tenant_name}", normal))
    elements.append(Paragraph(f"Unit: {unit_number}, {property_name}", normal))
    elements.append(Spacer(1, 12))

    body = (
        f"Please take notice that your tenancy for the above property is hereby terminated "
        f"effective {effective_date.strftime('%B %d, %Y')}, being a period of three (3) months "
        f"from the date of this notice."
    )
    elements.append(Paragraph(body, normal))
    elements.append(Spacer(1, 8))

    if reason:
        elements.append(Paragraph(f"Reason: {reason}", normal))
        elements.append(Spacer(1, 8))

    elements.append(Paragraph(
        "You are required to vacate the premises on or before the effective date stated above "
        "and hand over possession to the landlord. All outstanding rent and utility bills must "
        "be cleared before handover.",
        normal
    ))
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=10))
    elements.append(Paragraph(f"Generated on {date.today().strftime('%B %d, %Y')}", small))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
