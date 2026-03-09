"""
Sudoku Ultra — ML Service Entrypoint
"""

import os
import uvicorn

from app.main import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3003"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
