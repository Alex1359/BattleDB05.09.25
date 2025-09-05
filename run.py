import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))
import os
from app import create_app, db
from app import app

# Исправленный путь с обработкой отсутствующей PYTHONPATH
app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'app'))
os.environ['PYTHONPATH'] = app_path + os.pathsep + os.environ.get('PYTHONPATH', '')

app = create_app()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
