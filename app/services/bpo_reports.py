"""
Serviços para geração de relatórios BPO
========================================
Funções auxiliares para:
- Gerar PDFs de extrato
- Listar contas a pagar com status de boleto
- Enviar relatório semanal por email
"""

import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT


def gerar_extrato_diario_pdf(client, conta_id: str, conta_nome: str, data: datetime) -> bytes:
    """
    Gera PDF de extrato de movimentações do dia para uma conta específica.
    
    Formato igual ao relatório do Conta Azul.
    """
    # Buscar movimentações do dia via API
    data_str = data.strftime("%Y-%m-%d")
    
    # Endpoint: GET /v1/financeiro/eventos-financeiros/contas-a-pagar/buscar
    # e GET /v1/financeiro/eventos-financeiros/contas-a-receber/buscar
    
    despesas_response = client._request(
        "GET",
        "/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
        params={
            "pagina": 1,
            "tamanho_pagina": 100,
            "data_competencia_de": data_str,
            "data_competencia_ate": data_str,
            "ids_contas_financeiras": [conta_id]
        }
    )
    
    receitas_response = client._request(
        "GET",
        "/v1/financeiro/eventos-financeiros/contas-a-receber/buscar",
        params={
            "pagina": 1,
            "tamanho_pagina": 100,
            "data_competencia_de": data_str,
            "data_competencia_ate": data_str,
            "ids_contas_financeiras": [conta_id]
        }
    )
    
    despesas = despesas_response.get("itens", [])
    receitas = receitas_response.get("itens", [])
    
    # Criar PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#333333'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph(f"Relatório de extrato {data.strftime('%d/%m/%Y')} a {data.strftime('%d/%m/%Y')}", title_style))
    elements.append(Spacer(1, 12))
    
    # Cabeçalho da empresa
    elements.append(Paragraph(f"<b>Conta:</b> {conta_nome}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Tabela de movimentações
    table_data = [["Data", "Descrição", "Cliente/Fornecedor", "Situação", "Categoria", "Valor (R$)", "Saldo (R$)"]]
    
    saldo_atual = 0
    
    # Adicionar receitas
    for receita in receitas:
        valor = receita.get("valor_total_liquido", 0)
        saldo_atual += valor
        table_data.append([
            data.strftime("%d/%m/%Y"),
            receita.get("descricao", ""),
            receita.get("contato", {}).get("nome", ""),
            receita.get("status", ""),
            receita.get("categoria", {}).get("nome", ""),
            f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"{saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ])
    
    # Adicionar despesas
    for despesa in despesas:
        valor = despesa.get("valor_total_liquido", 0) * -1  # Despesa é negativa
        saldo_atual += valor
        table_data.append([
            data.strftime("%d/%m/%Y"),
            despesa.get("descricao", ""),
            despesa.get("contato", {}).get("nome", ""),
            despesa.get("status", ""),
            despesa.get("categoria", {}).get("nome", ""),
            f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            f"{saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        ])
    
    # Totais
    table_data.append([
        "Totais do período",
        "",
        "",
        "",
        "Desconsiderados: R$ 0,00",
        "Perdidos: R$ 0,00",
        f"Saldo Realizado: R$ {saldo_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    ])
    
    table = Table(table_data, colWidths=[25*mm, 40*mm, 35*mm, 25*mm, 30*mm, 25*mm, 25*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (5, 0), (6, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    elements.append(table)
    
    # Construir PDF
    doc.build(elements)
    
    return buffer.getvalue()


def listar_contas_a_pagar(client, data_vencimento_de: str, data_vencimento_ate: str, 
                          ids_contas_financeiras: list, incluir_status_boleto: bool = True) -> dict:
    """
    Lista contas a pagar com status do boleto (se tem código de barras nas observações).
    """
    response = client._request(
        "GET",
        "/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
        params={
            "pagina": 1,
            "tamanho_pagina": 100,
            "data_vencimento_de": data_vencimento_de,
            "data_vencimento_ate": data_vencimento_ate,
            "ids_contas_financeiras": ids_contas_financeiras,
            "status": ["EM_ABERTO", "ATRASADO"]
        }
    )
    
    contas = response.get("itens", [])
    
    # Enriquecer com status do boleto
    if incluir_status_boleto:
        for conta in contas:
            nota = conta.get("nota", "") or ""
            # Verificar se tem código de barras (sequência numérica longa)
            tem_codigo_barras = len([c for c in nota if c.isdigit()]) >= 44  # Boleto tem ~47 dígitos
            
            conta["status_boleto"] = {
                "lançado": tem_codigo_barras,
                "alerta": not tem_codigo_barras and (
                    datetime.strptime(conta.get("data_vencimento"), "%Y-%m-%d") - datetime.now()
                ).days <= 3
            }
    
    # Estatísticas
    total_valor = sum(c.get("valor_total_liquido", 0) for c in contas)
    total_lancados = sum(1 for c in contas if c.get("status_boleto", {}).get("lançado"))
    total_nao_lancados = len(contas) - total_lancados
    
    return {
        "periodo": {
            "de": data_vencimento_de,
            "ate": data_vencimento_ate
        },
        "resumo": {
            "total_contas": len(contas),
            "total_valor": total_valor,
            "boletos_lancados": total_lancados,
            "boletos_nao_lancados": total_nao_lancados,
            "alertas": sum(1 for c in contas if c.get("status_boleto", {}).get("alerta"))
        },
        "contas": contas
    }


def enviar_relatorio_semanal(client, company_id: int, email_destino: str) -> dict:
    """
    Envia relatório semanal de contas a pagar por email.
    """
    hoje = datetime.now()
    
    # Semana anterior (7 dias atrás até hoje)
    semana_passada_inicio = (hoje - timedelta(days=7)).strftime("%Y-%m-%d")
    semana_passada_fim = hoje.strftime("%Y-%m-%d")
    
    # Próxima semana (hoje até +7 dias)
    proxima_semana_inicio = hoje.strftime("%Y-%m-%d")
    proxima_semana_fim = (hoje + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Buscar contas da semana passada (pagas)
    contas_pagas = client._request(
        "GET",
        "/v1/financeiro/eventos-financeiros/contas-a-pagar/buscar",
        params={
            "pagina": 1,
            "tamanho_pagina": 100,
            "data_pagamento_de": semana_passada_inicio,
            "data_pagamento_ate": semana_passada_fim,
            "status": ["RECEBIDO"]
        }
    )
    
    # Buscar contas bancárias
    contas_bancarias = client.list_financial_accounts()
    ids_contas = [
        c["id"] for c in contas_bancarias.get("itens", [])
        if c.get("ativo") and c.get("tipo") in ["CONTA_CORRENTE", "OUTROS"]
    ]
    
    # Buscar contas da próxima semana
    resultado_proxima_semana = listar_contas_a_pagar(
        client=client,
        data_vencimento_de=proxima_semana_inicio,
        data_vencimento_ate=proxima_semana_fim,
        ids_contas_financeiras=ids_contas,
        incluir_status_boleto=True
    )
    
    # Montar email
    total_pagas = len(contas_pagas.get("itens", []))
    valor_pago = sum(c.get("valor_total_liquido", 0) for c in contas_pagas.get("itens", []))
    
    total_a_vencer = resultado_proxima_semana["resumo"]["total_contas"]
    valor_a_vencer = resultado_proxima_semana["resumo"]["total_valor"]
    alertas = resultado_proxima_semana["resumo"]["alertas"]
    
    assunto = f"Relatório Semanal - Contas a Pagar ({semana_passada_inicio} a {proxima_semana_fim})"
    
    corpo = f"""
<html>
<body style="font-family: Arial, sans-serif;">
    <h2>📊 Relatório Semanal - Contas a Pagar</h2>
    
    <h3>✅ SEMANA ANTERIOR ({semana_passada_inicio} a {semana_passada_fim})</h3>
    <p><b>Contas Pagas:</b> {total_pagas} contas | R$ {valor_pago:,.2f}</p>
    
    <h3>📅 PRÓXIMA SEMANA ({proxima_semana_inicio} a {proxima_semana_fim})</h3>
    <p><b>A Vencer:</b> {total_a_vencer} contas | R$ {valor_a_vencer:,.2f}</p>
    
    {"<p style='color: red;'><b>⚠️ ALERTAS:</b> " + str(alertas) + " boleto(s) não lançado(s) próximo(s) do vencimento</p>" if alertas > 0 else ""}
    
    <hr>
    <p><i>Relatório gerado automaticamente em {hoje.strftime('%d/%m/%Y às %H:%M')}</i></p>
    <p>Staff Consult</p>
</body>
</html>
    """
    
    # Enviar email
    enviar_email(
        destinatario=email_destino,
        assunto=assunto,
        corpo_html=corpo
    )
    
    return {
        "status": "success",
        "email_enviado": email_destino,
        "resumo": {
            "semana_passada": {"total_pagas": total_pagas, "valor": valor_pago},
            "proxima_semana": {"total_a_vencer": total_a_vencer, "valor": valor_a_vencer, "alertas": alertas}
        }
    }


def enviar_email(destinatario: str, assunto: str, corpo_html: str, anexos: list = None):
    """
    Envia email via SMTP.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    
    if not smtp_user or not smtp_password:
        raise ValueError("Credenciais SMTP não configuradas")
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = destinatario
    msg['Subject'] = assunto
    
    msg.attach(MIMEText(corpo_html, 'html'))
    
    # Anexos
    if anexos:
        for anexo in anexos:
            part = MIMEApplication(anexo['data'], Name=anexo['filename'])
            part['Content-Disposition'] = f'attachment; filename="{anexo["filename"]}"'
            msg.attach(part)
    
    # Enviar
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
