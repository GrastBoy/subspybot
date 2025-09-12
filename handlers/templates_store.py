import json
import os
from typing import Dict, Optional

TEMPLATES_FILE = os.getenv("TEMPLATES_FILE", "templates.json")

def _ensure_file():
    if not os.path.exists(TEMPLATES_FILE):
        with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "hello": "Вітаю! Готовий допомогти з реєстрацією.",
                "wait_code": "Надішлю код найближчим часом, будь ласка, очікуйте.",
                "after_code": "Будь ласка, введіть надісланий код у застосунку, а потім натисніть '📞 Номер підтверджено'."
            }, f, ensure_ascii=False, indent=2)

def load_templates() -> Dict[str, str]:
    _ensure_file()
    try:
        with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_templates(data: Dict[str, str]):
    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_templates() -> Dict[str, str]:
    return load_templates()

def get_template(key: str) -> Optional[str]:
    return load_templates().get(key)

def set_template(key: str, text: str):
    data = load_templates()
    data[key] = text
    save_templates(data)

def del_template(key: str) -> bool:
    data = load_templates()
    if key in data:
        del data[key]
        save_templates(data)
        return True
    return False