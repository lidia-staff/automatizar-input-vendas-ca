import pandas as pd
import unicodedata
from typing import List, Dict


# 🔒 Colunas CANÔNICAS (saída padronizada para o resto do sistema)
CANONICAL_COLUMNS = [
    "DATA ATENDIMENTO",
    "CLIENTE / PACIENTE",
    "CATEGORIA",
    "PRODUTOS/SERVIÇOS",
    "DETALHES DO ITEM",
    "QUANTIDADE",
    "VALOR UNITARIO",
    "FORMA DE PAGAMENTO",
    "CONTA DE RECEBIMENTO",
    "CONDICAO DE PAGAMENTO",
    "VENCIMENTO",
]

# ✅ Aliases aceitos por coluna (para suportar layouts reais)
ALIASES = {
    "DATA ATENDIMENTO": ["DATA ATENDIMENTO", "DATA", "DATA DA VENDA", "DATA VENDA"],
    "CLIENTE / PACIENTE": ["CLIENTE / PACIENTE", "CLIENTE", "PACIENTE", "NOME", "NOME DO CLIENTE"],
    "CATEGORIA": ["CATEGORIA", "CATEGORIAS"],
    "PRODUTOS/SERVIÇOS": ["PRODUTOS/SERVIÇOS", "PRODUTOS", "SERVICOS", "SERVIÇOS", "PRODUTOS SERVICOS", "PRODUTOS SERVIÇOS"],
    "DETALHES DO ITEM": ["DETALHES DO ITEM", "DETALHES", "OBS", "OBSERVACAO", "OBSERVAÇÃO"],
    "QUANTIDADE": ["QUANTIDADE", "QTD", "QTDE"],
    "VALOR UNITARIO": ["VALOR UNITARIO", "VALOR UNITÁRIO", "VALOR", "PRECO", "PREÇO", "VALOR UN"],
    "FORMA DE PAGAMENTO": ["FORMA DE PAGAMENTO", "PAGAMENTO", "MEIO DE PAGAMENTO"],
    "CONTA DE RECEBIMENTO": ["CONTA DE RECEBIMENTO", "CONTA", "CONTA RECEBIMENTO"],
    "CONDICAO DE PAGAMENTO": ["CONDICAO DE PAGAMENTO", "CONDIÇÃO DE PAGAMENTO", "CONDICAO", "CONDIÇÃO", "PARCELAS"],
    "VENCIMENTO": ["VENCIMENTO", "DATA VENCIMENTO", "VENC", "DUE DATE"],
}


def normalize_col(col: str) -> str:
    """
    Normaliza nomes de colunas para comparação robusta:
    - uppercase
    - remove acentos
    - troca '/', '-' '_' por espaço
    - remove múltiplos espaços
    """
    col = str(col).strip().upper()
    col = unicodedata.normalize("NFKD", col).encode("ASCII", "ignore").decode("ASCII")
    col = col.replace("/", " ").replace("-", " ").replace("_", " ")
    col = " ".join(col.split())
    return col


def _find_source_column(df_columns: List[str], canonical: str) -> str | None:
    """
    Dado um nome canônico, encontra a coluna real no dataframe usando aliases.
    Retorna o nome ORIGINAL da coluna no df ou None.
    """
    # mapa: normalizado -> original
    norm_map = {normalize_col(c): c for c in df_columns}

    # tenta pelo próprio canônico e aliases
    for alias in ALIASES.get(canonical, [canonical]):
        alias_norm = normalize_col(alias)
        if alias_norm in norm_map:
            return norm_map[alias_norm]
    return None


def read_base_sheet(file_path: str, sheet_name: str = "Base") -> List[Dict]:
    """
    Lê a planilha e devolve registros com colunas canônicas.
    - Aceita aliases (ex.: 'CLIENTE' vira 'CLIENTE / PACIENTE')
    - Loga abas/colunas/linhas para debug
    """
    xls = pd.ExcelFile(file_path, engine="openpyxl")

    # Escolha de aba com fallback
    if sheet_name not in xls.sheet_names:
        print(f"[IMPORT] Aba '{sheet_name}' não encontrada. Abas disponíveis: {xls.sheet_names}")
        sheet_name = xls.sheet_names[0]

    df = pd.read_excel(xls, sheet_name=sheet_name)
    print(f"[IMPORT] Usando aba: {sheet_name}")

    print(f"[IMPORT] Colunas originais: {list(df.columns)}")
    print(f"[IMPORT] Colunas normalizadas: {[normalize_col(c) for c in df.columns]}")
    print(f"[IMPORT] Total de linhas (bruto): {len(df)}")

    # Descobrir colunas fonte para cada coluna canônica
    source_cols = {}
    missing = []

    for canonical in CANONICAL_COLUMNS:
        src = _find_source_column(list(df.columns), canonical)
        if not src:
            missing.append(canonical)
        else:
            source_cols[canonical] = src

    if missing:
        raise ValueError(
            f"Colunas ausentes na planilha (canônicas): {missing}. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    # Monta DF padronizado
    df2 = df[[source_cols[c] for c in CANONICAL_COLUMNS]].copy()
    df2.columns = CANONICAL_COLUMNS

    # Remove linhas totalmente vazias
    before = len(df2)
    df2 = df2.dropna(how="all")
    after = len(df2)
    print(f"[IMPORT] Linhas antes limpeza: {before} | depois: {after}")

    # Conversões básicas (para evitar problemas downstream)
    # Datas
    for col in ["DATA ATENDIMENTO", "VENCIMENTO"]:
        df2[col] = pd.to_datetime(df2[col], errors="coerce").dt.date

    # Numéricos
    df2["QUANTIDADE"] = pd.to_numeric(df2["QUANTIDADE"], errors="coerce").fillna(0)
    df2["VALOR UNITARIO"] = pd.to_numeric(df2["VALOR UNITARIO"], errors="coerce").fillna(0)

    # Texto
    for col in ["CLIENTE / PACIENTE", "CATEGORIA", "PRODUTOS/SERVIÇOS", "DETALHES DO ITEM",
                "FORMA DE PAGAMENTO", "CONTA DE RECEBIMENTO", "CONDICAO DE PAGAMENTO"]:
        df2[col] = df2[col].astype(str).fillna("").map(lambda x: x.strip())

    records = df2.to_dict(orient="records")
    print(f"[IMPORT] Registros gerados: {len(records)}")

    return records