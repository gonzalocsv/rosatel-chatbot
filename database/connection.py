"""
================================================================================
                         CONEXIÓN A BIGQUERY
================================================================================
"""

from google.cloud import bigquery
from google.oauth2 import service_account
from functools import lru_cache
from typing import Optional
import json
import os

from config import get_settings


class BigQueryConnection:
    """Manejador de conexión a BigQuery"""
    
    _instance: Optional["BigQueryConnection"] = None
    _client: Optional[bigquery.Client] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa el cliente de BigQuery"""
        settings = get_settings()
        
        try:
            # Intentar con credenciales de archivo
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            
            if credentials_path and os.path.exists(credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path
                )
                self._client = bigquery.Client(
                    project=settings.google_project_id,
                    credentials=credentials
                )
            else:
                # Usar Application Default Credentials (ADC)
                self._client = bigquery.Client(
                    project=settings.google_project_id
                )
            
            print(f"Conectado a BigQuery: {settings.google_project_id}")
            
        except Exception as e:
            print(f"Error conectando a BigQuery: {e}")
            print("   Usando modo offline/demo")
            self._client = None
    
    @property
    def client(self) -> Optional[bigquery.Client]:
        return self._client
    
    @property
    def is_connected(self) -> bool:
        return self._client is not None
    
    def get_table_ref(self) -> str:
        """Obtiene la referencia completa a la tabla de productos"""
        settings = get_settings()
        return f"{settings.google_project_id}.{settings.bigquery_dataset}.{settings.bigquery_table}"
    
    def execute_query(self, query: str) -> list:
        """Ejecuta una consulta y retorna los resultados como lista de dicts"""
        if not self.is_connected:
            return []
        
        try:
            query_job = self._client.query(query)
            results = query_job.result()
            
            return [dict(row.items()) for row in results]
            
        except Exception as e:
            print(f"Error ejecutando query: {e}")
            return []


@lru_cache()
def get_bigquery_client() -> BigQueryConnection:
    """Obtiene la instancia singleton de BigQuery"""
    return BigQueryConnection()
