from flask import Blueprint, current_app, render_template, request, jsonify, redirect, url_for, flash
from wsproto import ConnectionType
from app.models import Battle, Battleparticipations, CommanderAssignment, MilitaryUnit, Country, Commander, UnitHierarchy, ConnectionType, BattleLosses
from app import db
from marshmallow import Schema, ValidationError, fields, validate, validates
from datetime import date, datetime
from sqlalchemy import or_, and_
from collections import deque

bp = Blueprint('units', __name__, url_prefix='/units')

class UnitSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    formation_date = fields.Date(allow_none=True, required=False)
    dissolution_date = fields.Date(allow_none=True, required=False)
    country_id = fields.Int(required=True)
    #parent_unit_id = fields.Int(allow_none=True)
    commander_id = fields.Int(allow_none=True, required=False)
    unit_type_id = fields.Int(allow_none=True, required=False)


    @validates('dissolution_date')
    def validate_dates(self, value, **kwargs):
        """
        Проверяет, что дата расформирования не раньше даты формирования.
        """
        # Получаем данные формы из kwargs
        data = kwargs.get('data', {})
        
        if not data:
            # Если данные не переданы (например, при partial load), пропускаем проверку
            return

        formation_date = data.get('formation_date')
        dissolution_date = value

        # Если обе даты заданы, проверяем их
        if formation_date and dissolution_date:
            # Убедимся, что это объекты date
            if isinstance(formation_date, str):
                try:
                    formation_date = datetime.strptime(formation_date, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    # Если не можем распарсить, пропускаем проверку дат
                    return
            if isinstance(dissolution_date, str):
                try:
                    dissolution_date = datetime.strptime(dissolution_date, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    # Если не можем распарсить, пропускаем проверку дат
                    return

            if dissolution_date < formation_date:
                raise ValidationError('Дата расформирования не может быть раньше даты формирования')
        
# Список всех подразделений
@bp.route('/units')
def list_units():
    unit_type = request.args.get('unit_type', type=int)
    country = request.args.get('country', type=int)
    target_date_str = request.args.get('date')
    focus_unit_id = request.args.get('focus_unit', type=int)

    # Преобразование даты
    target_date = None
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Некорректный формат даты. Используйте ГГГГ-ММ-ДД.', 'warning')

    # Базовый запрос
    query = MilitaryUnit.query

    if unit_type:
        query = query.filter_by(unit_type_id=unit_type)
    if country:
        query = query.filter_by(country_id=country)

    all_units = query.order_by(MilitaryUnit.name).all()
    # Для фильтра "Фокус на подразделение"
    all_units_for_focus_filter = MilitaryUnit.query.order_by(MilitaryUnit.name).all()

    top_level_units = []
    path_to_focus_unit = [] # Список ID от корня к фокусному юниту
    focus_unit_obj_for_context = None # Сам объект фокусного юнита для передачи в шаблон

    if focus_unit_id:
        focus_unit_obj_for_context = MilitaryUnit.query.get(focus_unit_id)
        if focus_unit_obj_for_context:
            # --- Логика построения пути ---
            # Используем словарь для быстрого поиска юнитов по ID
            unit_dict = {u.id: u for u in all_units}

            # Функция для безопасного поиска родителя на дату
            def get_parent_safe(unit_obj, date_obj):
                if not unit_obj or not date_obj:
                    return None
                try:
                    return unit_obj.get_parent_at_date(date_obj)
                except Exception:
                    return None

            # 1. Найти путь от фокусного юнита к корню
            visited = set()
            current = focus_unit_obj_for_context
            temp_date = target_date
            path_ids = [] # Путь от фокуса к корню (обратный)

            # Защита от зацикливания
            for _ in range(50):
                if current is None or current.id in visited:
                    break
                visited.add(current.id)
                path_ids.append(current.id)
                current = get_parent_safe(current, temp_date)

            # 2. Перевернуть путь, чтобы он шел от корня к фокусу
            path_to_focus_unit = list(reversed(path_ids))
            # --- Конец логики построения пути ---

            if path_to_focus_unit:
                # Корневой элемент пути - это первый элемент в списке
                root_id_in_path = path_to_focus_unit[0]
                root_unit_in_path = unit_dict.get(root_id_in_path)
                if root_unit_in_path:
                    # Передаем корневой элемент пути для отображения
                    # Логика шаблона должна знать, что это специальный режим
                    top_level_units = [root_unit_in_path]
                else:
                    top_level_units = []
                    flash('Корневой элемент пути не найден.', 'warning')
            else:
                 top_level_units = []
                 flash('Не удалось построить путь к выбранному подразделению.', 'warning')
        else:
             flash('Выбранное подразделение не найдено.', 'warning')
    else:
        # Стандартное поведение: показать все верхнеуровневые подразделения
        # с учетом фильтров и даты
        filtered_unit_ids = {u.id for u in all_units} # Оптимизация
        for unit in all_units:
            # Проверяем, есть ли родитель на указанную дату среди отфильтрованных юнитов
            parent = unit.get_parent_at_date(target_date)
            # Убедимся, что родитель тоже проходит фильтры
            if not parent or parent.id not in filtered_unit_ids:
                top_level_units.append(unit)

    return render_template(
        'units/list.html',
        all_units=all_units,
        top_level_units=top_level_units,
        unit_types=ConnectionType.query.all(),
        countries=Country.query.all(),
        connection_types=ConnectionType.query.all(),
        all_units_for_focus_filter=all_units_for_focus_filter,
        focus_unit_id=focus_unit_id, # Передаем ID фокусного юнита
        focus_unit_obj=focus_unit_obj_for_context, # Передаем объект фокусного юнита
        path_to_focus=path_to_focus_unit, # Передаем путь (список ID)
        target_date_for_template=target_date_str # Передаем дату
    )



# Форма добавления нового подразделения
# ... внутри def new_unit(): ...
# Форма добавления нового подразделения
# ... внутри def new_unit(): ...
@bp.route('/new', methods=['GET', 'POST'])
def new_unit():
    from app.models import Battle # Убедитесь, что Battle импортирован
    
    if request.method == 'POST':
        try:
            # Подготовим данные подразделения (без commander_id)
            form_data = request.form.to_dict()
            # Обработка дат и других полей
            if form_data.get('formation_date') == '':
                form_data['formation_date'] = None
            if form_data.get('dissolution_date') == '':
                form_data['dissolution_date'] = None
            if form_data.get('unit_type_id') == '':
                form_data['unit_type_id'] = None
            # Создаем временную схему или валидируем вручную
            # Для простоты, делаем минимальную проверку
            name = form_data.get('name', '').strip()
            country_id_str = form_data.get('country_id', '').strip()
            errors = []
            if not name:
                errors.append("Название подразделения обязательно.")
            if not country_id_str:
                errors.append("Страна обязательна.")
            try:
                country_id = int(country_id_str) if country_id_str else None
            except ValueError:
                country_id = None
                errors.append("Некорректный ID страны.")
            # Обработка дат
            formation_date = None
            dissolution_date = None
            if form_data.get('formation_date'):
                try:
                    formation_date = datetime.strptime(form_data['formation_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append("Некорректный формат даты формирования.")
            if form_data.get('dissolution_date'):
                try:
                    dissolution_date = datetime.strptime(form_data['dissolution_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append("Некорректный формат даты расформирования.")
            # Проверка логики дат
            if formation_date and dissolution_date and dissolution_date < formation_date:
                 errors.append('Дата расформирования не может быть раньше даты формирования.')
            if errors:
                 db.session.rollback()
                 flash(f"Ошибка в данных: {' '.join(errors)}", 'danger')
                 countries = Country.query.order_by(Country.name).all()
                 commanders = Commander.query.order_by(Commander.last_name, Commander.first_name).all()
                 unit_types = ConnectionType.query.order_by(ConnectionType.level).all()
                 # Загружаем все сражения для формы
                 all_battles = Battle.query.order_by(Battle.date_begin.desc()).all()
                 return render_template('units/new.html',
                                      countries=countries,
                                      commanders=commanders,
                                      unit_types=unit_types,
                                      all_battles=all_battles, # Передаем сражения
                                      form_data=request.form)
            # Создание основного подразделения
            unit = MilitaryUnit(
                name=name,
                formation_date=formation_date,
                dissolution_date=dissolution_date,
                country_id=country_id,
                unit_type_id=int(form_data['unit_type_id']) if form_data.get('unit_type_id') else None
            )
            db.session.add(unit)
            db.session.flush() # Получаем unit.id до коммита

            # --- Обработка истории командования ---
            # Собираем данные о назначениях из формы
            new_assignments_data = []
            assignment_counter = 0
            while True:
                # Ищем поля для текущего назначения
                commander_id_key = f'commander_id_{assignment_counter}'
                start_date_key = f'start_date_{assignment_counter}'
                end_date_key = f'end_date_{assignment_counter}'
                if commander_id_key not in request.form:
                    break # Больше нет назначений
                commander_id_val = request.form.get(commander_id_key)
                start_date_val = request.form.get(start_date_key)
                end_date_val = request.form.get(end_date_key)
                assignment_counter += 1
                # Обработка commander_id
                try:
                    commander_id = int(commander_id_val) if commander_id_val else None
                except ValueError:
                    commander_id = None
                    flash(f'Некорректный ID командира в назначении {assignment_counter}. Пропущено.', 'warning')
                    continue # Пропускаем это назначение
                if not commander_id:
                    flash(f'Не выбран командир в назначении {assignment_counter}. Пропущено.', 'warning')
                    continue
                # Обработка дат
                start_date = None
                end_date = None
                date_errors = []
                if start_date_val:
                    try:
                        start_date = datetime.strptime(start_date_val, '%Y-%m-%d').date()
                    except ValueError:
                        date_errors.append(f"Некорректная дата начала в назначении {assignment_counter}.")
                if end_date_val:
                    try:
                        end_date = datetime.strptime(end_date_val, '%Y-%m-%d').date()
                    except ValueError:
                        date_errors.append(f"Некорректная дата окончания в назначении {assignment_counter}.")
                if date_errors:
                    flash(' '.join(date_errors), 'warning')
                    continue # Пропускаем это назначение
                # Проверка логики дат назначения
                if start_date and end_date and end_date < start_date:
                    flash(f'Дата окончания не может быть раньше даты начала в назначении {assignment_counter}. Пропущено.', 'warning')
                    continue
                # Создание нового назначения
                new_assignment = CommanderAssignment(
                    unit_id=unit.id,
                    commander_id=commander_id,
                    Com_start=start_date,
                    Com_end=end_date
                )
                db.session.add(new_assignment)
            # --- Конец обработки истории командования ---

            # --- Обработка участия в сражениях ---
            # Предполагаем, что в форме есть поля battle_id_X и side_X, где X - индекс
            battle_counter = 0
            while True:
                battle_id_key = f'battle_id_{battle_counter}'
                side_key = f'side_{battle_counter}'

                if battle_id_key not in request.form:
                    break

                battle_id_val = request.form.get(battle_id_key)
                side_val = request.form.get(side_key, '').strip()

                battle_counter += 1

                if not battle_id_val:
                    # Пропускаем пустые строки
                    continue

                try:
                    battle_id = int(battle_id_val)
                except ValueError:
                    flash(f'Некорректный ID сражения в участии {battle_counter}. Пропущено.', 'warning')
                    continue

                # Проверка существования сражения (опционально)
                battle = Battle.query.get(battle_id)
                if not battle:
                    flash(f'Сражение с ID {battle_id} не найдено. Пропущено.', 'warning')
                    continue

                # Создание нового участия
                from app.models import Battleparticipations # Убедитесь, что импортировано
                new_participation = Battleparticipations(
                    battle_id=battle_id,
                    unit_id=unit.id,
                    side=side_val if side_val else None # Можно сделать обязательным
                )
                db.session.add(new_participation)

            # --- Конец обработки участия в сражениях ---

            db.session.commit()
            flash('Подразделение успешно добавлено', 'success')
            return redirect(url_for('units.list_units'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка при добавлении подразделения: {e}")
            flash(f'Ошибка при добавлении подразделения: {str(e)}', 'danger')
    # GET запрос
    countries = Country.query.order_by(Country.name).all()
    commanders = Commander.query.order_by(Commander.last_name, Commander.first_name).all()
    unit_types = ConnectionType.query.all()
    # Загружаем все сражения для формы
    all_battles = Battle.query.order_by(Battle.date_begin.desc()).all()
    return render_template('units/new.html', 
                         countries=countries,
                         commanders=commanders,
                         unit_types=unit_types,
                         all_battles=all_battles) # Передаем сражения


# Просмотр информации о подразделении
@bp.route('/<int:id>')
def view_unit(id):
    unit = MilitaryUnit.query.get_or_404(id)
    
    # История командования
    command_history = CommanderAssignment.query \
        .filter_by(unit_id=id) \
        .join(Commander) \
        .order_by(CommanderAssignment.Com_start.desc()) \
        .all()

    # Можно передать в шаблон, если нужно отдельно
    return render_template(
        'units/view.html',
        unit=unit,
        command_history=command_history
    )

# Редактирование подразделения
# Редактирование подразделения
# ... внутри def edit_unit(id): ...
@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_unit(id):
    from app.models import Battle, Battleparticipations # Убедитесь, что импортировано
    
    unit = MilitaryUnit.query.get_or_404(id)
    if request.method == 'POST':
        # --- Обработка основных данных подразделения ---
        # (Оставляем существующую логику для name, dates, country, unit_type)
        try:
            # Подготовим данные подразделения (без commander_id)
            form_data = request.form.to_dict()
            # Убираем потенциально конфликтующие ключи, если они есть
            form_data.pop('commander_assignments', None) # На случай, если в форме будет такой ключ
            # Обработка дат и других полей
            if form_data.get('formation_date') == '':
                form_data['formation_date'] = None
            if form_data.get('dissolution_date') == '':
                form_data['dissolution_date'] = None
            if form_data.get('unit_type_id') == '':
                form_data['unit_type_id'] = None
            # commander_id больше не используется напрямую
            # Создаем временную схему или валидируем вручную
            # Для простоты, делаем минимальную проверку
            name = form_data.get('name', '').strip()
            country_id_str = form_data.get('country_id', '').strip()
            errors = []
            if not name:
                errors.append("Название подразделения обязательно.")
            if not country_id_str:
                errors.append("Страна обязательна.")
            try:
                country_id = int(country_id_str) if country_id_str else None
            except ValueError:
                country_id = None
                errors.append("Некорректный ID страны.")
            # Обработка дат
            formation_date = None
            dissolution_date = None
            if form_data.get('formation_date'):
                try:
                    formation_date = datetime.strptime(form_data['formation_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append("Некорректный формат даты формирования.")
            if form_data.get('dissolution_date'):
                try:
                    dissolution_date = datetime.strptime(form_data['dissolution_date'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append("Некорректный формат даты расформирования.")
            # Проверка логики дат
            if formation_date and dissolution_date and dissolution_date < formation_date:
                 errors.append('Дата расформирования не может быть раньше даты формирования.')
            if errors:
                 db.session.rollback()
                 flash(f"Ошибка в данных: {' '.join(errors)}", 'danger')
                 # Повторно загружаем данные для отображения формы
                 countries = Country.query.order_by(Country.name).all()
                 commanders = Commander.query.order_by(Commander.last_name, Commander.first_name).all()
                 unit_types = ConnectionType.query.all()
                 parent_units = MilitaryUnit.query.filter(
                     MilitaryUnit.id != id,
                     MilitaryUnit.country_id == unit.country_id
                 ).all()
                 # Загружаем текущую историю командования
                 command_history = CommanderAssignment.query.filter_by(unit_id=id).order_by(CommanderAssignment.Com_start.desc()).all()
                 # Загружаем все сражения
                 all_battles = Battle.query.order_by(Battle.date_begin.desc()).all()
                 # Загружаем текущие участия в сражениях
                 battle_participations = Battleparticipations.query.filter_by(unit_id=id).all()
                 return render_template('units/edit.html',
                                      unit=unit,
                                      countries=countries,
                                      commanders=commanders,
                                      unit_types=unit_types,
                                      parent_units=parent_units,
                                      command_history=command_history, # Передаем историю
                                      all_battles=all_battles, # Передаем сражения
                                      battle_participations=battle_participations # Передаем текущие участия
                                      )
            # Обновление основных данных юнита
            unit.name = name
            unit.formation_date = formation_date
            unit.dissolution_date = dissolution_date
            unit.country_id = country_id
            unit.unit_type_id = int(form_data['unit_type_id']) if form_data.get('unit_type_id') else None
            # unit.commander_id = ... # Убираем
            # --- Обработка истории командования ---
            # Получаем данные из формы о назначениях
            # ... (оставляем существующую логику обработки истории командования) ...
            # Пример обработки (псевдокод, требует адаптации под фронтенд):
            # Это ПРИМЕР логики, фронтенд должен генерировать такие поля правильно
            # --- СЛОЖНЫЙ СПОСОБ: Редактирование всей истории ---
            # Это требует сложного фронтенда. Пока покажем, как можно обработать.
            # 1. Получить все существующие назначения для этого юнита
            existing_assignments = {a.id: a for a in CommanderAssignment.query.filter_by(unit_id=id).all()}
            # 2. Предположим, форма отправляет данные в виде:
            # assignment_ids[] - список ID существующих назначений (или 'new' для новых)
            # commander_id_X, start_date_X, end_date_X - где X - индекс или ID
            # Пример обработки (псевдокод, требует адаптации под фронтенд):
            # Это ПРИМЕР логики, фронтенд должен генерировать такие поля правильно
            assignment_counter = 0
            processed_assignment_ids = set() # Для отслеживания удаленных
            while True:
                # Ищем поля для текущего назначения
                assignment_id_key = f'assignment_id_{assignment_counter}'
                commander_id_key = f'commander_id_{assignment_counter}'
                start_date_key = f'start_date_{assignment_counter}'
                end_date_key = f'end_date_{assignment_counter}'
                delete_key = f'delete_{assignment_counter}' # Если есть флаг удаления
                if assignment_id_key not in request.form:
                    break # Больше нет назначений
                assignment_id_val = request.form.get(assignment_id_key)
                commander_id_val = request.form.get(commander_id_key)
                start_date_val = request.form.get(start_date_key)
                end_date_val = request.form.get(end_date_key)
                delete_flag = request.form.get(delete_key) # 'on' если отмечено
                assignment_counter += 1
                if delete_flag == 'on':
                    # Удаление назначения
                    if assignment_id_val and assignment_id_val != 'new':
                        assignment_to_delete = existing_assignments.get(int(assignment_id_val))
                        if assignment_to_delete:
                            db.session.delete(assignment_to_delete)
                            processed_assignment_ids.add(assignment_to_delete.id)
                    # Пропускаем создание/обновление
                    continue
                # Обработка commander_id
                try:
                    commander_id = int(commander_id_val) if commander_id_val else None
                except ValueError:
                    commander_id = None
                    flash(f'Некорректный ID командира в назначении {assignment_counter}. Пропущено.', 'warning')
                    continue # Пропускаем это назначение
                if not commander_id:
                    flash(f'Не выбран командир в назначении {assignment_counter}. Пропущено.', 'warning')
                    continue
                # Обработка дат
                start_date = None
                end_date = None
                date_errors = []
                if start_date_val:
                    try:
                        start_date = datetime.strptime(start_date_val, '%Y-%m-%d').date()
                    except ValueError:
                        date_errors.append(f"Некорректная дата начала в назначении {assignment_counter}.")
                if end_date_val:
                    try:
                        end_date = datetime.strptime(end_date_val, '%Y-%m-%d').date()
                    except ValueError:
                        date_errors.append(f"Некорректная дата окончания в назначении {assignment_counter}.")
                if date_errors:
                    flash(' '.join(date_errors), 'warning')
                    continue # Пропускаем это назначение
                # Проверка логики дат назначения
                if start_date and end_date and end_date < start_date:
                    flash(f'Дата окончания не может быть раньше даты начала в назначении {assignment_counter}. Пропущено.', 'warning')
                    continue
                # Создание или обновление
                if assignment_id_val == 'new':
                    # Создание нового назначения
                    new_assignment = CommanderAssignment(
                        unit_id=unit.id,
                        commander_id=commander_id,
                        Com_start=start_date,
                        Com_end=end_date
                    )
                    db.session.add(new_assignment)
                else:
                    # Обновление существующего
                    try:
                        existing_id = int(assignment_id_val)
                        assignment_to_update = existing_assignments.get(existing_id)
                        if assignment_to_update:
                            assignment_to_update.commander_id = commander_id
                            assignment_to_update.Com_start = start_date
                            assignment_to_update.Com_end = end_date
                            db.session.add(assignment_to_update)
                            processed_assignment_ids.add(assignment_to_update.id)
                        else:
                             flash(f'Назначение с ID {existing_id} не найдено. Пропущено.', 'warning')
                    except ValueError:
                        flash(f'Некорректный ID назначения {assignment_id_val}. Пропущено.', 'warning')
            # --- Конец обработки истории командования ---

            # --- Обработка участия в сражениях ---
            # Получаем все существующие участия для этого юнита
            existing_participations = {p.id: p for p in Battleparticipations.query.filter_by(unit_id=id).all()}
            processed_participation_ids = set()

            battle_counter = 0
            while True:
                # Ищем поля для текущего участия
                participation_id_key = f'participation_id_{battle_counter}'
                battle_id_key = f'battle_id_{battle_counter}'
                side_key = f'side_{battle_counter}'
                delete_key = f'delete_{battle_counter}' # Если будет флаг удаления

                # В простом случае проверяем наличие battle_id_key
                if battle_id_key not in request.form:
                    break

                participation_id_val = request.form.get(participation_id_key)
                battle_id_val = request.form.get(battle_id_key)
                side_val = request.form.get(side_key, '').strip()
                delete_flag = request.form.get(delete_key) # 'on' если отмечено

                battle_counter += 1

                # Логика удаления (если реализована через флаг)
                if delete_flag == 'on':
                    if participation_id_val and participation_id_val.isdigit():
                        participation_to_delete = existing_participations.get(int(participation_id_val))
                        if participation_to_delete:
                            db.session.delete(participation_to_delete)
                            processed_participation_ids.add(participation_to_delete.id)
                    continue

                if not battle_id_val:
                    # Пропускаем пустые строки
                    continue

                try:
                    battle_id = int(battle_id_val)
                except ValueError:
                    flash(f'Некорректный ID сражения в участии {battle_counter}. Пропущено.', 'warning')
                    continue

                # Проверка существования сражения (опционально)
                battle = Battle.query.get(battle_id)
                if not battle:
                    flash(f'Сражение с ID {battle_id} не найдено. Пропущено.', 'warning')
                    continue

                # Создание или обновление
                if not participation_id_val or participation_id_val == 'new' or not participation_id_val.isdigit():
                    # Создание нового участия
                    new_participation = Battleparticipations(
                        battle_id=battle_id,
                        unit_id=unit.id,
                        side=side_val if side_val else None
                    )
                    db.session.add(new_participation)
                else:
                    # Обновление существующего
                    try:
                        existing_id = int(participation_id_val)
                        participation_to_update = existing_participations.get(existing_id)
                        if participation_to_update:
                            participation_to_update.battle_id = battle_id
                            participation_to_update.side = side_val if side_val else None
                            db.session.add(participation_to_update)
                            processed_participation_ids.add(participation_to_update.id)
                        else:
                             flash(f'Участие с ID {existing_id} не найдено. Пропущено.', 'warning')
                    except ValueError:
                        flash(f'Некорректный ID участия {participation_id_val}. Пропущено.', 'warning')

            # --- Конец обработки участия в сражениях ---

            db.session.commit()
            flash('Изменения сохранены', 'success')
            return redirect(url_for('units.view_unit', id=unit.id))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Ошибка при сохранении изменений подразделения {id}: {e}")
            flash(f'Ошибка при сохранении изменений: {str(e)}', 'danger')
    # GET запрос
    countries = Country.query.order_by(Country.name).all()
    commanders = Commander.query.order_by(Commander.last_name, Commander.first_name).all()
    unit_types = ConnectionType.query.all()
    parent_units = MilitaryUnit.query.filter(
        MilitaryUnit.id != id,
        MilitaryUnit.country_id == unit.country_id
    ).all()
    # Загружаем текущую историю командования
    command_history = CommanderAssignment.query.filter_by(unit_id=id).order_by(CommanderAssignment.Com_start.desc()).all()
    # Загружаем все сражения
    all_battles = Battle.query.order_by(Battle.date_begin.desc()).all()
    # Загружаем текущие участия в сражениях
    battle_participations = Battleparticipations.query.filter_by(unit_id=id).all()
    return render_template('units/edit.html',
                         unit=unit,
                         countries=countries,
                         commanders=commanders,
                         unit_types=unit_types,
                         parent_units=parent_units,
                         command_history=command_history, # Передаем историю в шаблон
                         all_battles=all_battles, # Передаем сражения
                         battle_participations=battle_participations # Передаем текущие участия
                         )



# Удаление подразделения
@bp.route('/<int:id>/delete', methods=['POST'])
def delete_unit(id):
    unit = MilitaryUnit.query.get_or_404(id)
    
    try:
        # Перед удалением обнуляем parent_unit_id у дочерних подразделений
        MilitaryUnit.query.filter_by(parent_unit_id=id).update({'parent_unit_id': None})
        db.session.delete(unit)
        db.session.commit()
        flash('Подразделение успешно удалено', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении подразделения: {str(e)}', 'danger')
    
    return redirect(url_for('units.list_units'))

# API: Получение подразделений по стране (для AJAX)
@bp.route('/api/units_by_country', methods=['GET'])
def get_units_by_country():
    country_id = request.args.get('country_id')
    if not country_id:
        return jsonify({'error': 'Не указан country_id'}), 400
    
    units = MilitaryUnit.query.filter_by(country_id=country_id).order_by(MilitaryUnit.name).all()
    return jsonify([{'id': u.id, 'name': u.name} for u in units])

# API: Получение командующих по стране (для AJAX)
@bp.route('/api/commanders_by_country', methods=['GET'])
def get_commanders_by_country():
    country_id = request.args.get('country_id')
    if not country_id:
        return jsonify({'error': 'Не указан country_id'}), 400
    
    commanders = Commander.query.filter_by(country_id=country_id)\
        .order_by(Commander.last_name, Commander.first_name).all()
    return jsonify([{'id': c.id, 'name': f'{c.last_name} {c.first_name}'} for c in commanders])