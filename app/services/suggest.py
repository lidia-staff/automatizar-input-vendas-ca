from rapidfuzz import process, fuzz

PAYMENT_NORMALIZATION = {
    "PIX": "Conta Pix",
    "CARTAO": "Conta Cartao",
    "CARTAO CREDITO": "Conta Cartao",
    "CARTAO DEBITO": "Conta Cartao",
    "DINHEIRO": "Caixa",
    "TRANSFERENCIA": "Banco",
}

def suggest_receiving_account(payment_method: str) -> str | None:
    k = payment_method.strip().upper()
    return PAYMENT_NORMALIZATION.get(k)

def suggest_category(input_category: str, known_categories: list[str]) -> list[tuple[str, int]]:
    # retorna top 3 sugestões (categoria, score)
    if not input_category or not known_categories:
        return []
    return process.extract(input_category, known_categories, scorer=fuzz.WRatio, limit=3)
