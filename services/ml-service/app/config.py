"""
Sudoku Ultra — ML Service Configuration

Environment-based settings with sensible defaults for development.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """ML service configuration loaded from environment variables."""

    # Service
    SERVICE_NAME: str = "ml-service"
    VERSION: str = "0.1.0"
    PORT: int = 3003
    ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # CORS
    CORS_ORIGINS: str = "*"

    # MLflow
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "sudoku-ultra"

    # MLflow Model Registry — canonical names for all six production models
    MLFLOW_MODEL_CLASSIFIER: str = "difficulty-classifier"
    MLFLOW_MODEL_REGRESSION: str = "adaptive-regression"
    MLFLOW_MODEL_SCANNER: str = "digit-scanner"
    MLFLOW_MODEL_CLUSTERING: str = "skill-clustering"
    MLFLOW_MODEL_CHURN: str = "churn-predictor"
    MLFLOW_MODEL_GAN: str = "gan-generator"

    # Model paths
    MODEL_DIR: str = "ml/models"
    CLASSIFIER_MODEL_NAME: str = "difficulty-classifier"
    SCANNER_MODEL_NAME: str = "puzzle-scanner"

    # Game Service
    GAME_SERVICE_URL: str = "http://localhost:3001"

    # Database (for feature store)
    DATABASE_URL: str = "postgresql://sudoku:sudoku_dev_password@localhost:5432/sudoku_ultra"

    # Qdrant vector DB
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str = ""
    TECHNIQUES_COLLECTION: str = "techniques"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # LLM routing
    OLLAMA_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "mistral"                           # quick hints
    HF_INFERENCE_API_KEY: str = ""
    HF_INFERENCE_MODEL: str = "mistralai/Mistral-7B-Instruct-v0.3"  # deep explanations
    TUTOR_MAX_TOKENS: int = 512
    TUTOR_SESSION_TTL_SECS: int = 3600                      # 1-hour idle session expiry
    TUTOR_MEMORY_WINDOW: int = 10                           # last N exchanges kept

    # Circuit breaker (LLM failover)
    LLM_CIRCUIT_BREAKER_THRESHOLD: int = 3                  # failures before open
    LLM_CIRCUIT_BREAKER_WINDOW_SECS: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
