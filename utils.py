import random

def distribuisci_premio(wallet_address, premio):
    """
    Distribuisce il premio al wallet specificato in base a percentuali fisse.
    
    Parametri:
      - wallet_address: indirizzo del wallet dell'utente.
      - premio: un identificativo per il tipo di premio (es. "ruota").
    
    Restituisce:
      - None se non viene assegnato alcun premio (60% dei casi),
      - Un dizionario con "tipo": "token" e "quantita" se viene assegnato un premio in token (25% dei casi),
      - Un dizionario con "tipo": "altro" e "descrizione" per un premio di tipo "altro":
          - "un bonus misterioso" (10% dei casi),
          - "un premio esclusivo" (5% dei casi).
    """
    print(f"Distribuzione del premio '{premio}' al wallet {wallet_address}")
    
    chance = random.randint(1, 100)
    if chance <= 60:
        # 60% dei casi: nessun premio
        return None
    elif chance <= 85:
        # 25% dei casi: premio in token
        quantita = random.randint(1, 3)  # quantità tra 1 e 3
        return {"tipo": "token", "quantita": quantita}
    elif chance <= 95:
        # 10% dei casi: premio "altro" - bonus misterioso
        return {"tipo": "altro", "descrizione": "un bonus misterioso"}
    else:
        # 5% dei casi: premio "altro" - premio esclusivo
        return {"tipo": "altro", "descrizione": "un premio esclusivo"}
