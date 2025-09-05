import os
import uuid
from flask import Blueprint, current_app, json, render_template, request, jsonify, redirect, url_for, flash, session
from app.models import Battle, BattleDiagram, Battleparticipations, Country, DiagramForm, MilitaryUnit, Commander, Place, SizeParties, Trophy, BattleLosses, get_next_battle_id
from app import db
from marshmallow import Schema, ValidationError, fields, validate, validates
from datetime import datetime, time
from sqlalchemy import and_, asc, func, or_
from geoalchemy2.functions import ST_AsGeoJSON
from datetime import datetime, time
from dateutil import parser
from sqlalchemy.orm import joinedload
from werkzeug.utils import secure_filename

bp = Blueprint('battles', __name__, url_prefix='/battles')

class BattleSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=3, max=100))
    date_begin = fields.Date(required=True)
    date_end = fields.Date(allow_none=True)
    description = fields.Str(allow_none=True)
    place_id = fields.Int(allow_none=True)
    victory = fields.Str(allow_none=True)

    #@validates('date_end')
    #def validate_dates(self, value, data, **kwargs):
        #if value and 'date_begin' in data and data['date_begin']:
           # if value < data['date_begin']:
              # raise ValidationError('Дата окончания не может быть раньше даты начала')

class participationsSchema(Schema):
    side = fields.Str(required=True, validate=validate.OneOf(['allies', 'axis', 'other']))
    unit_id = fields.Int(required=True)
    commander_id = fields.Int(allow_none=True)
    

class LossSchema(Schema):
    type = fields.Str(required=True, validate=validate.OneOf(['killed', 'wounded', 'captured']))
    count = fields.Int(required=True, validate=validate.Range(min=1))

class TrophySchema(Schema):
    type = fields.Str(required=True)
    description = fields.Str(allow_none=True)
    quantity = fields.Int(validate=validate.Range(min=1), load_default=1)
    captor_id = fields.Int(required=True)

# Список всех сражений
@bp.route('/')
def list_battles():
    battles = db.session.query(
        Battle.id,
        Battle.name,
        Battle.date_begin,
        Battle.date_end,
        Battle.victory,
        Place.name.label('place_name'),
        func.ST_AsGeoJSON(Place.geom).label('geom_json')
    ).join(Place).order_by(asc(Battle.date_begin).nulls_first())
    
    battles_data = []
    for battle in battles:
        # Безопасное преобразование даты для исторических дат
        timestamp = 0
        date_str = None
        
        if battle.date_begin:
            try:
                # Преобразуем в строку и обратно для унификации
                date_str = battle.date_begin.strftime('%Y-%m-%d')
                dt = parser.parse(date_str)
                # Альтернативный метод расчета timestamp
                timestamp = (dt - datetime(1970, 1, 1)).total_seconds()
            except Exception as e:
                current_app.logger.error(f"Error processing date for battle {battle.id}: {str(e)}")
                timestamp = 0
        
        battles_data.append({
            'id': battle.id,
            'name': battle.name,
            'date': date_str if date_str else None,
            'timestamp': int(timestamp),
            'victory': battle.victory,
            'place_name': battle.place_name,
            'geom': json.loads(battle.geom_json) if battle.geom_json else None
        })
    
    return render_template('battles/list.html', battles=battles_data)

# Многошаговая форма добавления сражения
@bp.route('/new', methods=['GET', 'POST'])
def new_battle():
    if request.method == 'GET':
        # Очистка сессии
        session.pop('battle_data', None)
        session.pop('participations_data', None)
        session.pop('losses_data', None)
        session.pop('trophies_data', None)

        countries = Country.query.order_by(Country.name).all()
        places = Place.query.order_by(Place.name).all()

        return render_template('battles/wizard_step1.html',
                               battle_data=session.get('battle_data', {}),
                               countries=countries,
                               places=places)

    if request.method == 'POST':
        step = request.form.get('step')
        if not step:
            flash("Неизвестный шаг", "danger")
            return redirect(url_for('battles.new_battle'))

        if step == '1':
            try:
                form_data = request.form.to_dict()

                # Удаляем лишние поля, которых нет в модели Battle
                form_data.pop('step', None)
                form_data.pop('csrf_token', None)  # если используется Flask-WTF

                # Обработка даты окончания
                if form_data.get('date_end') == '':
                    form_data['date_end'] = None

                form_data.pop('id', None)

                session['battle_data'] = form_data
                return redirect(url_for('battles.new_battle_step2'))

            except Exception as e:
                flash(f'Ошибка: {str(e)}', 'danger')
                return redirect(url_for('battles.new_battle'))

            
@bp.route('/new/step2', methods=['GET', 'POST'])
def new_battle_step2():
    if 'battle_data' not in session:
        return redirect(url_for('battles.new_battle'))

    if request.method == 'GET':
        battle_data = session.get('battle_data', {})
        participationss = session.get('participationss_data', [])
        countries = Country.query.order_by(Country.name).all()
        units = MilitaryUnit.query.join(Country).order_by(MilitaryUnit.name).all()
        commanders = Commander.query.join(Country).order_by(Commander.last_name, Commander.first_name).all()

        return render_template('battles/wizard_step2.html',
                               battle=battle_data,
                               participationss=participationss,
                               countries=countries,
                               units=units,
                               commanders=commanders)

    if request.method == 'POST':
        step = request.form.get('step')
        if step == '2':
            try:
                participant_list = []
                i = 0
                while f'participations-{i}-country_id' in request.form:
                    part_data = {
                        'country_id': request.form[f'participations-{i}-country_id'],
                        'unit_id': request.form[f'participations-{i}-unit_id'],
                        'commander_id': request.form.get(f'participations-{i}-commander_id'),
                    }
                    participant_list.append(part_data)
                    i += 1

                session['participations_data'] = participant_list
                return redirect(url_for('battles.new_battle_step3'))

            except Exception as e:
                flash(f'Ошибка при сохранении данных об участниках: {str(e)}', 'danger')
                return redirect(url_for('battles.new_battle_step2'))


@bp.route('/new/step3', methods=['GET', 'POST'])
def new_battle_step3():
    if 'battle_data' not in session or 'participationss_data' not in session:
        return redirect(url_for('battles.new_battle'))

    if request.method == 'POST':
        try:
            loss_data = {
                'killed': request.form.get('killed', 0, type=int),
                'wounded': request.form.get('wounded', 0, type=int),
                'captured': request.form.get('captured', 0, type=int),
                'guns_lost': request.form.get('guns_lost', 0, type=int),
                'colours_lost': request.form.get('colours_lost', 0, type=int),
            }

            session['losses_data'] = loss_data
            return save_complete_battle()

        except Exception as e:
            flash(f'Ошибка при сохранении данных о потерях: {str(e)}', 'danger')
            return redirect(url_for('battles.new_battle_step3'))

    losses_data = session.get('losses_data', {
        'killed': 0,
        'wounded': 0,
        'captured': 0,
        'guns_lost': 0,
        'colours_lost': 0
    })

    trophies = session.get('trophies_data', [])
    return render_template(
        'battles/wizard_step3.html',
        battle=session.get('battle_data', {}),
        participationss=session.get('participationss_data', []),
        losses_data=losses_data,
        trophies=trophies
    )

@bp.route('/save-complete', methods=['POST'])
def save_complete_battle():
    try:
        # Создаём сражение
        battle_data = session.get('battle_data', {})
        battle = Battle(**battle_data)
        db.session.add(battle)
        db.session.flush()  # Получаем battle.id

        # Участники
        for p in session.get('participationss_data', []):
            participant = Battleparticipations(battle_id=battle.id, **p)
            db.session.add(participant)

        # Трофеи
        for t in session.get('trophies_data', []):
            trophy = Trophy(battle_id=battle.id, **t)
            db.session.add(trophy)

        # Потери (общие по сражению)
        losses_data = session.get('losses_data', {})
        if losses_data:
            loss = BattleLosses(battle_id=battle.id, **losses_data)
            db.session.add(loss)

        db.session.commit()
        flash('Сражение успешно сохранено!', 'success')

        # Очистка сессии
        session.pop('battle_data', None)
        session.pop('participationss_data', None)
        session.pop('losses_data', None)
        session.pop('trophies_data', None)

        return redirect(url_for('battles.view_battle', id=battle.id))

    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при сохранении: {str(e)}', 'danger')
        return redirect(url_for('battles.new_battle_step3'))

# Просмотр информации о сражении
@bp.route('/<int:id>')
def view_battle(id):
    battle = Battle.query.options(
        db.joinedload(Battle.place),
        # Загружаем участников и связанные объекты
        db.joinedload(Battle.participations).joinedload(Battleparticipations.unit),
        db.joinedload(Battle.participations).joinedload(Battleparticipations.commander),
        # ... другие опции ...
    ).get_or_404(id)
    participations = Battleparticipations.query.filter_by(battle_id=id).all()
    
    # Получаем численность сторон
    size_entries = (SizeParties.query
                    .filter_by(battle_id=id)
                    .options(joinedload(SizeParties.country),
                              joinedload(SizeParties.source))
                    .all())
    
    # Группируем по сторонам
    french_size = next((s for s in size_entries if s.country.name == 'France'), None)
    allied_size = [s for s in size_entries if s.country.name != 'France']

    # Участники сражения
    french_participants = []
    other_participants = []
    
    for p in participations:
        if p.unit and p.unit.country and p.unit.country.name == 'France':
            french_participants.append(p)
        else:
            other_participants.append(p)
    
    
    # Потери: собираем ВСЕ записи BattleLosses для этого сражения
    all_losses = BattleLosses.query.filter_by(battle_id=id).all()
    
    french_losses = []
    allied_losses = []
    
    for loss in all_losses:
        if not loss.country:  # Пропускаем, если нет страны
            continue
        
        # Формируем запись с потерями (включая NULL/0)
        loss_data = {
            'killed': loss.killed,
            'wounded': loss.wounded,
            'captured': loss.captured,
            'missing': loss.missing,
            'killed_wounded': loss.killed_wounded
        }
        
        # Проверяем, есть ли хоть одно ненулевое значение
        has_data = any(
            val is not None and val != 0
            for val in loss_data.values()
        )
        
        if not has_data:
            continue
        
        # Разделяем на французов и союзников
        if loss.country.name == 'France':
            french_losses.append({
                'country': loss.country,
                'data': loss_data
            })
        else:
            allied_losses.append({
                'country': loss.country,
                'data': loss_data
            })

    trophies = Trophy.query.filter_by(battle_id=id).all()

    return render_template(
        'battles/view.html',
        battle=battle,
        french_size=french_size,
        allied_size=allied_size,
        french_participants=french_participants,
        other_participants=other_participants,
        french_losses=french_losses,
        allied_losses=allied_losses,
        trophies=trophies
    )

# Редактирование сражения (упрощенная версия)
@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_battle(id):
    battle = Battle.query.get_or_404(id)

    if request.method == 'POST':
        try:
            form_data = request.form.to_dict()

            # Обработка даты
            if form_data.get('date_end') == '':
                form_data['date_end'] = None

            # Обновляем поля битвы
            battle.name = form_data.get('name')
            battle.date_begin = form_data.get('date_begin')
            battle.date_end = form_data.get('date_end')
            battle.description = form_data.get('description')
            battle.place_id = form_data.get('place_id')

            # ✅ Обновление участников
            unit_ids = request.form.getlist('unit_ids')

            # Удаляем старые связи
            Battleparticipations.query.filter_by(battle_id=id).delete()

            # Добавляем новые
            for unit_id in unit_ids:
                participation = Battleparticipations(
                    battle_id=id,
                    unit_id=int(unit_id)
                )
                db.session.add(participation)

            db.session.commit()
            flash('Изменения сохранены', 'success')
            return redirect(url_for('battles.view_battle', id=battle.id))

        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении изменений: {str(e)}', 'danger')

    places = Place.query.order_by(Place.name).all()
    participants = Battleparticipations.query.filter_by(battle_id=id).all()
    french_units = MilitaryUnit.query.join(Country).filter(Country.name == 'France').all()
    other_units = MilitaryUnit.query.join(Country).filter(Country.name != 'France').all()

    return render_template(
        'battles/edit.html',
        battle=battle,
        places=places,
        french_units=french_units,
        other_units=other_units,
        participants=participants
    )
# Удаление сражения
@bp.route('/<int:id>/delete', methods=['POST'])
def delete_battle(id):
    battle = Battle.query.get_or_404(id)
    
    try:
        # Удаляем связанные данные
        Battleparticipations.query.filter_by(battle_id=id).delete()
        Trophy.query.filter_by(battle_id=id).delete()
        
        db.session.delete(battle)
        db.session.commit()
        flash('Сражение успешно удалено', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении сражения: {str(e)}', 'danger')
    
    return redirect(url_for('battles.list_battles'))

# API: Поиск мест (для автодополнения)
@bp.route('/api/search_places', methods=['GET'])
def search_places():
    query = request.args.get('query', '')
    
    if len(query) < 2:
        return jsonify([])
    
    places = Place.query.filter(Place.name.ilike(f'%{query}%')).limit(10).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'coordinates': f"{p.latitude}, {p.longitude}" if p.latitude and p.longitude else ''
    } for p in places])

@bp.route('/search')
def search_battles():
    query = request.args.get('q', '')
    # Реализация поиска офицеров
    results = Battle.query.filter(
        or_(
            Battle.name.ilike(f'%{query}%'),
            Battle.date_begin.ilike(f'%{query}%')
        )
    ).all()
    return render_template('battles/list.html', battles=results)

@bp.route('/battle/<int:battle_id>/add_diagram', methods=['GET', 'POST'])
def add_diagram(battle_id):
    battle = Battle.query.get_or_404(battle_id)
    form = DiagramForm()
    
    if form.validate_on_submit():
        # Сохранение файла
        file = form.diagram.data
        filename = secure_filename(f"battle_{battle_id}_{uuid.uuid4().hex[:8]}_{file.filename}")
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'battle_diagrams', filename)
        
        # Создаем папку если нет
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        
        # Если отмечаем как основную, снимаем флаг у других
        if form.is_main.data:
            BattleDiagram.query.filter_by(battle_id=battle_id).update({'is_main': False})
        
        # Создаем запись в БД
        diagram = BattleDiagram(
            battle_id=battle_id,
            filename=filename,
            description=form.description.data,
            is_main=form.is_main.data
        )
        db.session.add(diagram)
        db.session.commit()
        
        flash('Схема успешно добавлена', 'success')
        return redirect(url_for('battles.view_battle', id=battle_id))
    
    return render_template('add_diagram.html', battle=battle, form=form)

@bp.route('/diagram/<int:diagram_id>/set_main', methods=['POST'])
def set_main_diagram(diagram_id):
    diagram = BattleDiagram.query.get_or_404(diagram_id)
    
    # Снимаем флаг у всех схем этого сражения
    BattleDiagram.query.filter_by(battle_id=diagram.battle_id).update({'is_main': False})
    
    # Устанавливаем флаг текущей схеме
    diagram.is_main = True
    db.session.commit()
    
    flash('Основная схема обновлена', 'success')
    return redirect(url_for('battles.view_battle', id=diagram.battle_id))

@bp.route('/diagram/<int:diagram_id>/delete', methods=['POST'])
def delete_diagram(diagram_id):
    diagram = BattleDiagram.query.get_or_404(diagram_id)
    battle_id = diagram.battle_id
    
    # Удаляем файл
    try:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], 'battle_diagrams', diagram.filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        current_app.logger.error(f"Error deleting diagram file: {e}")
    
    # Удаляем запись из БД
    db.session.delete(diagram)
    db.session.commit()
    
    flash('Схема удалена', 'success')
    return redirect(url_for('battles.view_battle', id=battle_id))