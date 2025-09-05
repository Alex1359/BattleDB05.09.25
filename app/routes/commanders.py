from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_migrate import history
from app.models import Battleparticipations, Commander, CommanderAssignment, CommanderRank, Country, MilitaryRank, MilitaryUnit, UnitHierarchy
from app import db
from marshmallow import Schema, fields, validate, ValidationError, validates
from datetime import datetime
from app.services.commander_service import CommanderService
from flask import render_template, url_for
from sqlalchemy import or_, text
from sqlalchemy.orm import joinedload

bp = Blueprint('commanders', __name__, url_prefix='/commanders')

class CommanderSchema(Schema):
    id = fields.Int(dump_only=True)
    first_name = fields.Str(required=True)
    last_name = fields.Str(required=True)
    birth_date = fields.Date(allow_none=True)
    death_date = fields.Date(allow_none=True)
    biography = fields.Str(allow_none=True)
    country_id = fields.Int(required=True, data_key="nationally_id")  # Связываем с моделью
    rank_id = fields.Int(allow_none=True)

    @validates('death_date')
    def validate_death_date(self, value, **kwargs):
        if not value:
            return
        if value > datetime.now().date():
            raise ValidationError("Дата смерти не может быть в будущем")
        if 'birth_date' in self.context and self.context['birth_date'] and value < self.context['birth_date']:
            raise ValidationError("Дата смерти должна быть после даты рождения")
        
# Список всех командующих
@bp.route('/commanders', methods=['GET'])
def list_commanders():
    # Получаем параметры фильтрации
    last_name = request.args.get('last_name', '')
    country_id = request.args.get('country', type=int)
    
    # Формируем базовый запрос
    query = Commander.query.options(db.joinedload(Commander.country))
    
    # Применяем фильтры
    if last_name:
        query = query.filter(Commander.last_name.ilike(f'%{last_name}%'))
    if country_id:
        query = query.filter(Commander.country_id == country_id)
    
    # Получаем список всех стран для фильтра
    countries = Country.query.order_by(Country.name).all()
    
    # Пагинация
    page = request.args.get('page', 1, type=int)
    per_page = 20
    commanders = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template(
        'commanders/list.html',
        commanders=commanders,
        countries=countries  # Передаем список стран в шаблон
    )

# Форма добавления нового командующего
@bp.route('/new', methods=['GET', 'POST'])
def new_commander():
    form_data = request.form if request.method == 'POST' else None
    countries = Country.query.order_by(Country.name).all()
    
    if request.method == 'POST':
        try:
            # Получаем данные формы
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            birth_date = request.form.get('birth_date') or None
            death_date = request.form.get('death_date') or None
            country_id = int(request.form.get('country_id'))
            biography = request.form.get('biography')

            # Проверка обязательных полей
            if not last_name:
                raise ValueError("Фамилия обязательна для заполнения")

            # Создаём нового командира
            commander = Commander(
                first_name=first_name,
                last_name=last_name,
                birth_date=birth_date,
                death_date=death_date,
                country_id=country_id,
                biography=biography
            )
            db.session.add(commander)
            db.session.flush()  # чтобы получить id

            # Обработка истории званий
            history_rank_ids = request.form.getlist('history_rank_ids[]')
            history_dates = request.form.getlist('history_dates[]')

            for i in range(len(history_rank_ids)):
                rank_id = history_rank_ids[i]
                date_str = history_dates[i]

                if not rank_id or not date_str:
                    continue

                try:
                    date_promoted = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    flash(f"Неверный формат даты: {date_str}", "danger")
                    continue

                # Добавляем повышение
                rank_entry = CommanderRank(
                    commander_id=commander.id,
                    rank_id=int(rank_id),
                    date_promoted=date_promoted
                )
                db.session.add(rank_entry)

            db.session.commit()
            flash("Командующий успешно добавлен", "success")
            return redirect(url_for('commanders.view_commander', id=commander.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении: {str(e)}", "danger")
            return render_template(
                'commanders/new.html',
                countries=countries,
                form_data=form_data
            )

    return render_template(
        'commanders/new.html',
        countries=countries,
        form_data=form_data
    )

# Просмотр информации о командующем
@bp.route('/<int:id>', methods=['GET'])
def view_commander(id):
    # Получаем командующего с предзагруженными связями
    commander = Commander.query.options(
        db.joinedload(Commander.country),
        db.joinedload(Commander.battle_participations).joinedload(Battleparticipations.battle),
        db.joinedload(Commander.battle_participations).joinedload(Battleparticipations.unit),
        db.joinedload(Commander.military_units).joinedload(CommanderAssignment.unit)
    ).get_or_404(id)

    # Исправленный запрос для истории званий
    rank_query = text("""
        SELECT mr.rank_name AS rank_name, co.name AS country_name, cr.date_promoted
        FROM commander_ranks cr
        JOIN military_ranks mr ON cr.rank_id = mr.id
        LEFT JOIN countries co ON mr.country_id = co.id
        WHERE cr.commander_id = :commander_id
        ORDER BY cr.date_promoted DESC;
    """)
    
    # Исправленный способ получения результатов
    rank_result = db.session.execute(rank_query, {"commander_id": id})
    # Преобразуем результат в список словарей
    commander_rank_history = [
        {
            "rank_name": row[0],
            "country_name": row[1],
            "date_promoted": row[2]
        }
        for row in rank_result
    ]

    return render_template(
        'commanders/view.html',
        commander=commander,
        commander_rank_history=commander_rank_history
    )

# Редактирование командующего
@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_commander(id):
    commander = Commander.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Основные данные командира
            commander.last_name = request.form.get('last_name')
            commander.first_name = request.form.get('first_name') or None
            commander.birth_date = request.form.get('birth_date') or None
            commander.death_date = request.form.get('death_date') or None
            commander.country_id = int(request.form.get('country_id'))
            commander.biography = request.form.get('biography')

            # Получаем историю званий
            history_entry_ids = request.form.getlist('history_entry_ids[]')
            history_rank_ids = request.form.getlist('history_rank_ids[]')
            history_dates = request.form.getlist('history_dates[]')

            # Удаляем все текущие повышения (для упрощения)
            CommanderRank.query.filter_by(commander_id=id).delete()

            # Сохраняем новые/обновлённые записи
            for i in range(len(history_rank_ids)):
                rank_id = history_rank_ids[i]
                date_str = history_dates[i]

                if not rank_id or not date_str:
                    continue

                date_promoted = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                new_rank = CommanderRank(
                    commander_id=id,
                    rank_id=int(rank_id),
                    date_promoted=date_promoted
                )
                db.session.add(new_rank)

            db.session.commit()
            flash("Изменения сохранены", "success")
            return redirect(url_for('commanders.view_commander', id=id))

        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при сохранении: {str(e)}", "danger")

    ranks = MilitaryRank.query.filter_by(country_id=commander.country_id).all()
    commander_rank_history = CommanderRank.query.filter_by(commander_id=id).all()

    return render_template(
        'commanders/edit.html',
        commander=commander,
        countries=Country.query.all(),
        ranks=ranks,
        commander_rank_history=commander_rank_history
    )


# Удаление командующего
@bp.route('/<int:id>/delete', methods=['POST'])
def delete_commander(id):
    commander = Commander.query.get_or_404(id)
    
    try:
        db.session.delete(commander)
        db.session.commit()
        flash('Командующий успешно удален', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении командующего: {str(e)}', 'danger')
    
    return redirect(url_for('commanders.list_commanders'))

# API: Получение званий по стране (для AJAX)
@bp.route('/api/ranks', methods=['GET'])
def get_ranks_api():
    country_id = request.args.get('country_id', type=int)
    if not country_id:
        return jsonify([])
    
    ranks = MilitaryRank.query.filter_by(country_id=country_id).order_by(MilitaryRank.rank_name).all()
    return jsonify([{'id': r.id, 'name': r.rank_name} for r in ranks])

# API: Поиск командующих (для автодополнения)
@bp.route('/api/search', methods=['GET'])
def search_commanders():
    query = request.args.get('query', '')
    
    if len(query) < 2:
        return jsonify([])
    
    commanders = Commander.query.filter(
        (Commander.last_name.ilike(f'%{query}%')) |
        (Commander.first_name.ilike(f'%{query}%'))
    ).limit(10).all()
    
    return jsonify([{
        'id': c.id,
        'name': f'{c.last_name} {c.first_name}',
        'country': c.country.name if c.country else ''
    } for c in commanders])

def detail(commander_id):
    commander = CommanderService.get_commander_with_ranks(commander_id)
    ranks = MilitaryRank.query.order_by(MilitaryRank.rank_level).all()
    return render_template('commanders/detail.html',
                         commander=commander,
                         available_ranks=ranks)

@bp.route('/<int:commander_id>/add_rank', methods=['POST'])
def add_rank(commander_id):
    rank_id = request.form.get('rank_id')
    promotion_date = request.form.get('promotion_date')
    
    try:
        CommanderService.add_rank_to_commander(commander_id, rank_id, promotion_date)
        flash('Звание успешно добавлено', 'success')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')
    
    return redirect(url_for('commanders.detail', commander_id=commander_id))

