from dotenv import load_dotenv
import os

load_dotenv()

def key_or_pass(att:str) -> str:

    minio= {
        'key':os.getenv('MINIO_KEY'),
        'password':os.getenv('MINIO_SECRET')
    }

    chave = att.lower()

    if chave not in minio:
        raise ValueError(f"Atributo inválido: {att}. Use 'key' ou 'password'.")

    valor = minio[chave]

    if valor is None:                       
        raise ValueError(f"'{att}' ausente no .env.")
    
    return valor

    
