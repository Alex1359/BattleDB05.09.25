import os
from pathlib import Path
import sys

# Опционально: добавить в путь, но часто не нужно
sys.path.append(str(Path(__file__).parent))

# УДАЛИ ЭТУ СТРОКУ:
# from app import app   ← УДАЛИ ЭТУ СТРОКУ

from app import create_app, db

# Создаём приложение через фабричный метод
app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
