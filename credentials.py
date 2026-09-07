from dotenv import load_dotenv
import os

load_dotenv()

class Credentials:
    @staticmethod
    def endpoints() -> dict:
        
        return {
            "minio": os.getenv("MINIO_ENDPOINT", "http://localhost:9100"),
            "kafka": os.getenv("KAFKA_BOOTSTRAP", "localhost:9092"),
        }

    @staticmethod
    def minio() -> dict:
        key = os.getenv("MINIO_KEY")
        secret = os.getenv("MINIO_SECRET")

        if not key or not secret:    
            raise ValueError("MINIO_KEY/MINIO_SECRET ausentes no .env.")
        return {"key": key, "secret": secret}

    
