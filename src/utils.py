import json
import os
import logging
from typing import Any, Optional

def load_json(file_path: str) -> Optional[Any]:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        logging.warning(f"File not found: {file_path}")
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON in file: {file_path}")
    return None

def save_json(data: Any, file_path: str) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
