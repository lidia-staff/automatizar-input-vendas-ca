"""
Rotas para automação BPO Financeiro
====================================
Endpoints para rotinas diárias automatizadas:
- Extrato diário (Stone + Asaas)
- Contas a pagar
- Relatório semanal
"""

import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
import io

from app.services.conta_azul_client import ContaAzulClient
from app.services.bpo_reports import (
    gerar_extrato_diario_pdf,
    listar_contas_a_pagar,
    enviar_relatorio_semanal
)

router = APIRouter(tags=["bpo"], prefix="/api/bpo")


@router.get("/extrato-diario")
async def extrato_diario(
    company_id: int = Query(..., description="ID da empresa no banco"),
    data: str = Query(None, description="Data do extrato (YYYY-MM-DD). Default: D-1 útil")
):
    """
    Gera PDFs de extrato de movimentações do Conta Azul para cada conta bancária.
    
    **Body Face:** Gera 2 PDFs (Stone Conta Corrente + Asaas)
    
    **Execução automática:** Todo dia 17h via Apps Script
    """
    try:
        # Se não passar data, usa D-1 útil
        if not data:
            data_extrato = datetime.now() - timedelta(days=1)
            # TODO: implementar lógica de dia útil
        else:
            data_extrato = datetime.strptime(data, "%Y-%m-%d")
        
        client = ContaAzulClient(company_id)
        
        # Buscar contas financeiras da empresa
        contas = client.list_financial_accounts()
        
        # Filtrar apenas contas bancárias ativas
        # Body Face: Stone Conta Corrente + Asaas
        contas_bancarias = [
            c for c in contas.get("itens", [])
            if c.get("ativo") and c.get("tipo") in ["CONTA_CORRENTE", "OUTROS"]
        ]
        
        if not contas_bancarias:
            raise HTTPException(status_code=404, detail="Nenhuma conta bancária encontrada")
        
        # Gerar PDF para cada conta
        pdfs_gerados = []
        for conta in contas_bancarias:
            pdf_bytes = gerar_extrato_diario_pdf(
                client=client,
                conta_id=conta["id"],
                conta_nome=conta["nome"],
                data=data_extrato
            )
            
            pdfs_gerados.append({
                "conta": conta["nome"],
                "filename": f"{data_extrato.strftime('%d-%m-%Y')}_CONCILIACAO_BANCARIA_{conta['nome'].upper().replace(' ', '_')}.pdf",
                "size": len(pdf_bytes)
            })
        
        return {
            "status": "success",
            "company_id": company_id,
            "data": data_extrato.strftime("%Y-%m-%d"),
            "pdfs_gerados": pdfs_gerados,
            "message": f"{len(pdfs_gerados)} extrato(s) gerado(s) com sucesso"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar extrato: {str(e)}")


@router.get("/contas-a-pagar")
async def contas_a_pagar(
    company_id: int = Query(..., description="ID da empresa no banco"),
    data_vencimento_de: str = Query(..., description="Data inicial (YYYY-MM-DD)"),
    data_vencimento_ate: str = Query(..., description="Data final (YYYY-MM-DD)"),
    incluir_status_boleto: bool = Query(True, description="Incluir status do boleto (tem código de barras?)")
):
    """
    Lista contas a pagar filtradas por período e contas bancárias.
    
    **Body Face:** Filtra apenas Stone Conta Corrente + Asaas
    
    **Status do boleto:**
    - ✅ Lançado: Tem código de barras no campo 'nota'
    - ⚠️ Falta lançar: NÃO tem código de barras no campo 'nota'
    """
    try:
        client = ContaAzulClient(company_id)
        
        # Buscar contas bancárias da empresa
        contas = client.list_financial_accounts()
        contas_bancarias = [
            c for c in contas.get("itens", [])
            if c.get("ativo") and c.get("tipo") in ["CONTA_CORRENTE", "OUTROS"]
        ]
        
        ids_contas = [c["id"] for c in contas_bancarias]
        
        # Chamar API Conta Azul para listar despesas
        resultado = listar_contas_a_pagar(
            client=client,
            data_vencimento_de=data_vencimento_de,
            data_vencimento_ate=data_vencimento_ate,
            ids_contas_financeiras=ids_contas,
            incluir_status_boleto=incluir_status_boleto
        )
        
        return resultado
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar contas a pagar: {str(e)}")


@router.post("/relatorio-semanal")
async def relatorio_semanal(
    company_id: int = Query(..., description="ID da empresa no banco"),
    email_destino: str = Query(..., description="Email para envio do relatório")
):
    """
    Envia relatório semanal de contas a pagar por email.
    
    **Conteúdo:**
    - Resumo da semana anterior (contas pagas)
    - Próxima semana (contas a vencer)
    - Alertas (boletos não lançados próximos do vencimento)
    
    **Execução automática:** Sábado 12h via Apps Script
    """
    try:
        client = ContaAzulClient(company_id)
        
        resultado = enviar_relatorio_semanal(
            client=client,
            company_id=company_id,
            email_destino=email_destino
        )
        
        return resultado
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar relatório: {str(e)}")
