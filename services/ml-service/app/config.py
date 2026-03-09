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

    # Model paths
    MODEL_DIR: str = "ml/models"
    CLASSIFIER_MODEL_NAME: str = "difficulty-classifier"
    SCANNER_MODEL_NAME: str = "puzzle-scanner"

    # Game Service
    GAME_SERVICE_URL: str = "http://localhost:3001"

    # Database (for feature store)
    DATABASE_URL: str = "postgresql://sudoku:sudoku_dev_password@localhost:5432/sudoku_ultra"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
