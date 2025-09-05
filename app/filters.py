# app/filters.py
from flask import current_app
from datetime import datetime

def unique_filter(items):
    """Jinja2 фильтр для удаления дубликатов в списке объектов"""
    seen = set()
    result = []
    for item in items:
        item_id = getattr(item, 'id', None)
        if item_id not in seen:
            seen.add(item_id)
            result.append(item)
    return result

def init_app(app):
    """Регистрация фильтров в приложении"""
    app.jinja_env.filters['unique'] = unique_filter

def escapejs(value):
    """Фильтр для экранирования JavaScript-кода."""
    if value is None:
        return ''
    # Экранируем специальные символы для JavaScript
    return (
        value
        .replace('\\', '\\\\')
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace('\n', '\\n')
        .replace('\r', '\\r')
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
    )

def strftime(date, fmt='%Y-%m-%d'):
    """Фильтр для форматирования даты"""
    if date is None:
        return ''
    return date.strftime(fmt)

def init_app(app):
    app.jinja_env.filters['strftime'] = strftime

# Добавляем фильтр в Flask
def register_filters(app):
    app.add_template_filter(escapejs, name='escapejs')