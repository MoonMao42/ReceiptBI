"""PyInstaller entry point."""
import os
import sys

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from app.main import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "18080"))
    uvicorn.run(app, host=host, port=port, log_level="info")
