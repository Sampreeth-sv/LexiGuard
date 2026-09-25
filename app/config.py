from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False
    )
    
    # GenAI
    gemini_api_key: str = Field(default='', alias='GEMINI_API_KEY')
    gemini_model: str = Field(default='gemini-3.6-flash', alias='GEMINI_MODEL')
    
    # Application
    app_host: str = '0.0.0.0'
    app_port: int = 8000
    debug: bool = False
    secret_key: str = 'change_this_to_a_random_secret_key'
    cors_origins: str = Field(
        default='http://localhost:8000,http://127.0.0.1:8000',
        alias='CORS_ORIGINS',
    )
    
    # Storage
    db_path: str = './lexiguard.db'
    upload_temp_dir: str = './tmp_uploads'
    
    # File Limits
    max_upload_size_mb: int = 10
    allowed_extensions: List[str] = ['pdf', 'docx', 'txt']
    
    # Retrieval weights (must sum to 1.0)
    weight_lexical: float = 0.45
    weight_tfidf: float = 0.30
    weight_structural: float = 0.15
    weight_clause_type: float = 0.10
    retrieval_top_k: int = 8
    retrieval_min_score: float = 0.05
    
    # LLM limits
    llm_max_context_tokens: int = 6000
    
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]
    
    @property
    def genai_available(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key != 'your_gemini_api_key_here')

settings = Settings()
