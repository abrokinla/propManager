import io
import logging
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)


def generate_tenancy_agreement(document_data: dict, signature_name: str = None, signed_date: date = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, spaceAfter=20, textColor=HexColor('#1a1a2e'))
    heading_style = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=13, spaceAfter=10, spaceBefore=16, textColor=HexColor('#16213e'))
    normal = ParagraphStyle('Normal2', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=6)
    bold = ParagraphStyle('Bold2', parent=normal, fontName='Helvetica-Bold')
    small = ParagraphStyle('Small2', parent=normal, fontSize=9, textColor=HexColor('#555555'))
    signature_style = ParagraphStyle('Signature', parent=normal, fontSize=12, leading=18, spaceAfter=4, textColor=HexColor('#1a1a2e'))

    elements = []
    elements.append(Paragraph("TENANCY AGREEMENT", title_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=HexColor('#0f3460'), spaceAfter=16))

    parties = document_data.get('parties', {})
    property_info = document_data.get('property', {})
    financial = document_data.get('financial_terms', {})
    obligations = document_data.get('obligations', {})
    termination = document_data.get('termination', {})

    elements.append(Paragraph("Parties", heading_style))
    elements.append(Paragraph(f"<b>Landlord:</b> {parties.get('landlord_name', 'N/A')}", normal))
    elements.append(Paragraph(f"<b>Tenant:</b> {parties.get('tenant_name', 'N/A')}", normal))

    elements.append(Paragraph("Property", heading_style))
    elements.append(Paragraph(f"<b>Address:</b> {property_info.get('address', 'N/A')}", normal))
    elements.append(Paragraph(f"<b>Unit:</b> {property_info.get('unit_number', 'N/A')}", normal))

    elements.append(Paragraph("Financial Terms", heading_style))
    data = [
        ['Annual Rent', f"₦{float(financial.get('annual_rent', 0)):,.2f}"],
        ['Security Deposit', f"₦{float(financial.get('security_deposit', 0)):,.2f}"],
        ['Payment Due Date', str(financial.get('payment_due_date', 'N/A'))],
        ['Late Payment Fee', f"₦{float(financial.get('late_fee', 0)):,.2f}" if financial.get('late_fee') else 'N/A'],
    ]
    t = Table(data, colWidths=[6*cm, 8*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#cccccc')),
        ('BACKGROUND', (0, 0), (0, -1), HexColor('#f0f0f0')),
    ]))
    elements.append(t)

    elements.append(Paragraph("Term", heading_style))
    elements.append(Paragraph(f"<b>Start Date:</b> {financial.get('lease_start', 'N/A')}", normal))
    elements.append(Paragraph(f"<b>Expiry Date:</b> {financial.get('lease_expiry', 'N/A')}", normal))
    elements.append(Paragraph(f"<b>Duration:</b> {financial.get('duration', 'N/A')}", normal))

    elements.append(Paragraph("Obligations", heading_style))
    elements.append(Paragraph(f"<b>Landlord Obligations:</b><br/>{obligations.get('landlord', 'N/A')}", normal))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(f"<b>Tenant Obligations:</b><br/>{obligations.get('tenant', 'N/A')}", normal))

    if termination:
        elements.append(Paragraph("Termination", heading_style))
        elements.append(Paragraph(f"<b>Notice Period:</b> {termination.get('notice_period', 'N/A')}", normal))
        elements.append(Paragraph(f"<b>Early Termination Fee:</b> {termination.get('early_termination_fee', 'N/A')}", normal))
        if termination.get('conditions'):
            elements.append(Paragraph(f"<b>Conditions:</b> {termination['conditions']}", normal))

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=10))
    elements.append(Paragraph(f"Generated on {date.today().strftime('%B %d, %Y')}", small))

    if signature_name and signed_date:
        elements.append(Spacer(1, 30))
        elements.append(HRFlowable(width="60%", thickness=1, color=HexColor('#0f3460'), spaceAfter=10))
        elements.append(Paragraph("SIGNATURE", ParagraphStyle('SigTitle', parent=title_style, fontSize=14, spaceAfter=10)))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(f"Signed by: <b>{signature_name}</b>", signature_style))
        elements.append(Paragraph(f"Date: <b>{signed_date.strftime('%B %d, %Y')}</b>", signature_style))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("This document has been electronically signed by the tenant.", normal))
        elements.append(HRFlowable(width="60%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=10))

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
