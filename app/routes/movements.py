from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from app.models import Place, UnitMovement, MilitaryUnit
from app import db
from marshmallow import Schema, fields, validate

bp = Blueprint('movements', __name__, url_prefix='/movements')

class PlaceSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    latitude = fields.Float(allow_none=True)
    longitude = fields.Float(allow_none=True)

class MovementSchema(Schema):
    id = fields.Int(dump_only=True)
    unit_id = fields.Int(required=True)
    start_place_id = fields.Int(required=True)
    end_place_id = fields.Int(required=True)
    date = fields.Date(required=True)
    distance_km = fields.Float(validate=validate.Range(min=0), allow_none=True)
    route_description = fields.Str(allow_none=True)

# Список всех мест
@bp.route('/places', methods=['GET'])
def list_places():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    places = Place.query.order_by(
        Place.name
    ).paginate(page=page, per_page=per_page)
    
    return render_template('movements/places.html', places=places)

# Добавление нового места
@bp.route('/places/new', methods=['GET', 'POST'])
def new_place():
    if request.method == 'POST':
        schema = PlaceSchema()
        try:
            data = schema.load(request.form)
            
            place = Place(
                name=data['name'],
                latitude=data.get('latitude'),
                longitude=data.get('longitude')
            )
            
            db.session.add(place)
            db.session.commit()
            flash('Место успешно добавлено', 'success')
            return redirect(url_for('movements.list_places'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении места: {str(e)}', 'danger')
    
    return render_template('movements/new_place.html')

# Редактирование места
@bp.route('/places/<int:id>/edit', methods=['GET', 'POST'])
def edit_place(id):
    place = Place.query.get_or_404(id)
    
    if request.method == 'POST':
        schema = PlaceSchema()
        try:
            data = schema.load(request.form)
            
            place.name = data['name']
            place.latitude = data.get('latitude')
            place.longitude = data.get('longitude')
            
            db.session.commit()
            flash('Изменения сохранены', 'success')
            return redirect(url_for('movements.list_places'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении изменений: {str(e)}', 'danger')
    
    return render_template('movements/edit_place.html', place=place)

# Список всех перемещений
@bp.route('/', methods=['GET'])
def list_movements():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    movements = UnitMovement.query.order_by(
        UnitMovement.date.desc()
    ).paginate(page=page, per_page=per_page)
    
    return render_template('movements/list.html', movements=movements)

# Добавление нового перемещения
@bp.route('/new', methods=['GET', 'POST'])
def new_movement():
    if request.method == 'POST':
        schema = MovementSchema()
        try:
            data = schema.load(request.form)
            
            movement = UnitMovement(
                unit_id=data['unit_id'],
                start_place_id=data['start_place_id'],
                end_place_id=data['end_place_id'],
                date=data['date'],
                distance_km=data.get('distance_km'),
                route_description=data.get('route_description')
            )
            
            db.session.add(movement)
            db.session.commit()
            flash('Перемещение успешно добавлено', 'success')
            return redirect(url_for('movements.list_movements'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении перемещения: {str(e)}', 'danger')
    
    units = MilitaryUnit.query.order_by(MilitaryUnit.name).all()
    places = Place.query.order_by(Place.name).all()
    
    return render_template('movements/new.html',
                         units=units,
                         places=places)

# Просмотр информации о перемещении
@bp.route('/<int:id>', methods=['GET'])
def view_movement(id):
    movement = UnitMovement.query.get_or_404(id)
    return render_template('movements/view.html', movement=movement)

# Редактирование перемещения
@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
def edit_movement(id):
    movement = UnitMovement.query.get_or_404(id)
    
    if request.method == 'POST':
        schema = MovementSchema()
        try:
            data = schema.load(request.form)
            
            movement.unit_id = data['unit_id']
            movement.start_place_id = data['start_place_id']
            movement.end_place_id = data['end_place_id']
            movement.date = data['date']
            movement.distance_km = data.get('distance_km')
            movement.route_description = data.get('route_description')
            
            db.session.commit()
            flash('Изменения сохранены', 'success')
            return redirect(url_for('movements.view_movement', id=movement.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при сохранении изменений: {str(e)}', 'danger')
    
    units = MilitaryUnit.query.order_by(MilitaryUnit.name).all()
    places = Place.query.order_by(Place.name).all()
    
    return render_template('movements/edit.html',
                         movement=movement,
                         units=units,
                         places=places)

# Удаление перемещения
@bp.route('/<int:id>/delete', methods=['POST'])
def delete_movement(id):
    movement = UnitMovement.query.get_or_404(id)
    
    try:
        db.session.delete(movement)
        db.session.commit()
        flash('Перемещение успешно удалено', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении перемещения: {str(e)}', 'danger')
    
    return redirect(url_for('movements.list_movements'))

# API: Получение координат места
@bp.route('/api/place_coordinates/<int:id>', methods=['GET'])
def get_place_coordinates(id):
    place = Place.query.get_or_404(id)
    return jsonify({
        'latitude': place.latitude,
        'longitude': place.longitude
    })

@bp.route('/api/create-place', methods=['POST'])
def api_create_place():
    data = request.get_json()
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Invalid data'}), 400
    
    try:
        new_place = Place(
            name=data['name'],
            latitude=data.get('latitude'),
            longitude=data.get('longitude')
        )
        db.session.add(new_place)
        db.session.commit()
        
        return jsonify({
            'id': new_place.id,
            'name': new_place.name,
            'latitude': new_place.latitude,
            'longitude': new_place.longitude
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500