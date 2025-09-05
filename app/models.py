from flask_wtf import FlaskForm
from marshmallow import validates
from sqlalchemy import or_, text
from wtforms import BooleanField, TextAreaField
from app import db
from datetime import datetime
from geoalchemy2 import Geometry
from datetime import date
from flask_wtf.file import FileField, FileAllowed, FileRequired

class Country(db.Model):
    __tablename__ = 'countries'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    
    # Отношения
    commanders = db.relationship('Commander', back_populates='country')
    military_units = db.relationship('MilitaryUnit', back_populates='country')
    military_ranks = db.relationship('MilitaryRank', back_populates='country')
    losses = db.relationship("BattleLosses", back_populates="country")
    size_entries = db.relationship('SizeParties')

class MilitaryRank(db.Model):
    __tablename__ = 'military_ranks'
    
    id = db.Column(db.Integer, primary_key=True)
    rank_name = db.Column(db.String(100), nullable=False)
    rank_level = db.Column(db.Integer)
    
    # Внешние ключи
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=False)
    
    # Отношения
    country = db.relationship('Country', back_populates='military_ranks')
    assignments = db.relationship(
        'CommanderRank', 
        back_populates='rank',
        foreign_keys='CommanderRank.rank_id'  # Явное указание
    )

class Commander(db.Model):
    __tablename__ = 'commanders'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    birth_date = db.Column(db.Date)
    death_date = db.Column(db.Date)
    biography = db.Column(db.Text)

    # Внешние ключи
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=False)
    rank_id = db.Column(db.Integer, db.ForeignKey('commander_ranks.id'))
    

    # Отношения
    country = db.relationship('Country', back_populates='commanders')
    battle_participations = db.relationship('Battleparticipations', back_populates='commander', cascade='all, delete-orphan'
    )

    # Звания
    rank_assignments = db.relationship(
        'CommanderRank',
        back_populates='commander',
        foreign_keys='CommanderRank.commander_id',
        order_by='desc(CommanderRank.date_promoted)',
        cascade='all, delete-orphan'
    )

    @property
    def current_rank(self):
        return self.rank_assignments[0].rank if self.rank_assignments else None

    # Командование подразделениями через CommanderAssignment
    military_units = db.relationship(
        'CommanderAssignment',
        back_populates='commander',
        foreign_keys='CommanderAssignment.commander_id',
        cascade='all, delete-orphan'
    )

class MilitaryUnit(db.Model):
    __tablename__ = 'military_units'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    formation_date = db.Column(db.Date)
    dissolution_date = db.Column(db.Date)
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=False)
    unit_type_id = db.Column(db.Integer, db.ForeignKey('connection_type.id'))

    # Отношения
    country = db.relationship('Country', back_populates='military_units')
    unit_type = db.relationship('ConnectionType', back_populates='military_units')


    commanders = db.relationship(
        'CommanderAssignment',
        back_populates='unit',
        foreign_keys='CommanderAssignment.unit_id',
        cascade='all, delete-orphan'
    )

    battle_participations = db.relationship('Battleparticipations', back_populates='unit')
    movements = db.relationship('UnitMovement', back_populates='unit')

    # Иерархия подразделений
    subordination_history = db.relationship(
        'UnitHierarchy',
         foreign_keys='UnitHierarchy.unit_id',
        back_populates='unit'
    )

    children_relations = db.relationship(
        'UnitHierarchy',
        foreign_keys='UnitHierarchy.parent_unit_id',
        back_populates='parent_unit'
    )

    @property
    def parents(self):
        """Безопасное получение родительских подразделений"""
        try:
            today = date.today()
            hierarchies = UnitHierarchy.query.filter(
                UnitHierarchy.unit_id == self.id,
                UnitHierarchy.start_date <= today,
                (UnitHierarchy.end_date.is_(None) | (UnitHierarchy.end_date >= today))
            ).all()
            
            # Фильтруем None и проверяем наличие parent_unit
            return [h.parent_unit for h in hierarchies if h and h.parent_unit]
        except Exception:
            return []  # В случае ошибки возвращаем пустой список

    def get_parent_at_date(self, target_date):
        """Более надёжный поиск родителя на дату"""
        if not target_date:
            return None
        
        # Ищем самую актуальную запись на указанную дату
        parent_link = db.session.query(UnitHierarchy, MilitaryUnit)\
            .join(MilitaryUnit, UnitHierarchy.parent_unit_id == MilitaryUnit.id)\
            .filter(
                UnitHierarchy.unit_id == self.id,
                UnitHierarchy.start_date <= target_date,
                or_(
                    UnitHierarchy.end_date.is_(None),
                    UnitHierarchy.end_date >= target_date
                )
            )\
            .order_by(UnitHierarchy.start_date.desc())\
            .first()
        
        return parent_link.MilitaryUnit if parent_link else None

    def get_hierarchy_level(self, target_date=None):
        """Возвращает уровень вложенности на выбранную дату"""
        level = 0
        current = self
        while True:
            parent = current.get_parent_at_date(target_date)
            if not parent:
                break
            level += 1
            current = parent
        return level

    @property
    def current_children(self):
        """Возвращает дочерние подразделения, актуальные на сегодня"""
        today = date.today()
        return [
            rel.unit for rel in self.children_relations
            if rel.start_date <= today and (rel.end_date is None or rel.end_date >= today)
        ]

    @property
    def all_children(self):
        """Все дочерние подразделения без учёта дат"""
        return [rel.unit for rel in self.children_relations]
    
    def get_children_at_date(self, target_date=None):
        """Возвращает дочерние подразделения на указанную дату"""
        if target_date is None:
            target_date = date.today()
        else:
            target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
        
        return [
            rel.unit for rel in self.children_relations
            if rel.start_date <= target_date and 
            (rel.end_date is None or rel.end_date >= target_date)
        ]
    
    def get_level(self):
        """Возвращает уровень подразделения на основе его типа"""
        if self.unit_type and self.unit_type.level is not None:
            return self.unit_type.level
        return 0  # Значение по умолчанию, если уровень не определён 
    
    def get_full_hierarchy_name(self, target_date=None):
        """
        Возвращает полное иерархическое название подразделения на указанную дату.
        Формат: 'Корпус — Дивизия — Бригада'
        Без добавления type (пехота, кавалерия).
        """
        if target_date is None:
            # Если дата не указана — возвращаем только имя текущего подразделения
            return self.name

        if isinstance(target_date, datetime):
            target_date = target_date.date()

        hierarchy = []
        current = self
        max_depth = 10  # Защита от циклов

        while current and max_depth > 0:
            max_depth -= 1
            # Добавляем ТОЛЬКО name, без type
            hierarchy.append(current.name.strip())
            # Ищем родителя на указанную дату
            parent = current.get_parent_at_date(target_date)
            if not parent:
                break
            current = parent

        print(f"[DEBUG] Строим иерархию для {self.name} на дату {target_date}")
        print(f"[DEBUG] Иерархия: {' — '.join(reversed(hierarchy))}")

        return " — ".join(reversed(hierarchy))

       
    def has_cyclic_dependency(self):
        """Безопасная проверка циклических зависимостей с защитой от None"""
        seen_ids = set()
        current = self
        max_depth = 100  # Защита от бесконечных циклов
        depth = 0
        
        while depth < max_depth:
            # Получаем родителей с проверкой на None
            parents = getattr(current, 'parents', [])
            if not parents or not isinstance(parents, (list, tuple)):
                return False
                
            for parent in parents:
                # Проверяем что parent не None и имеет id
                if not parent or not hasattr(parent, 'id'):
                    continue
                    
                if parent.id == self.id:  # Нашли цикл
                    return True
                    
                if parent.id in seen_ids:  # Уже видели этот ID
                    return True
                    
                seen_ids.add(parent.id)
                current = parent
                break  # Проверяем только один путь
            else:
                return False
                
            depth += 1
            
        return False  # Слишком глубокая иерархия, считаем что цикла нет

class UnitHierarchy(db.Model):
    __tablename__ = 'unit_hierarchy'

    id_history = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('military_units.id'), nullable=False)
    parent_unit_id = db.Column(db.Integer, db.ForeignKey('military_units.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)

    # Отношения
    unit = db.relationship(
        'MilitaryUnit',
        foreign_keys=[unit_id],
        back_populates='subordination_history'
    )

    parent_unit = db.relationship(
        'MilitaryUnit',
        foreign_keys=[parent_unit_id],
        back_populates='children_relations'
    )

    __table_args__ = (
        db.Index('idx_unit_parent', 'unit_id', 'parent_unit_id'),
        db.Index('idx_dates', 'start_date', 'end_date'),
    )

    @validates('parent_unit_id')
    def validate_parent(self, key, parent_unit_id):
        if parent_unit_id == self.unit_id:
            raise ValueError("Подразделение не может быть родителем самого себя")
        
        # Проверка на циклические зависимости
        current = MilitaryUnit.query.get(parent_unit_id)
        while current:
            if current.id == self.unit_id:
                raise ValueError("Обнаружена циклическая зависимость")
            current = current.parents[0] if current.parents else None
            
        return parent_unit_id
    
    __table_args__ = (
    db.Index('idx_unit_hierarchy_for_dates', 'unit_id', 'start_date', 'end_date'),
)

class BattleLosses(db.Model):
    __tablename__ = 'battle_losses'

    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey('battles.id'), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=False)

    killed = db.Column(db.Integer, default=0)
    wounded = db.Column(db.Integer, default=0)
    captured = db.Column(db.Integer, default=0)
    missing = db.Column(db.Integer, default=0)
    killed_wounded = db.Column(db.Integer, default=0)

    # Отношения
    battle = db.relationship("Battle", back_populates="losses_by_country")
    country = db.relationship("Country", back_populates="losses")


class Battle(db.Model):
    __tablename__ = 'battles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date_begin = db.Column(db.Date, nullable=False)
    date_end = db.Column(db.Date)
    description = db.Column(db.Text)
    victory = db.Column(db.String(40))

    # Внешние ключи
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'))
    
    # Отношения
    place = db.relationship('Place', back_populates='battles')
    participations = db.relationship('Battleparticipations', back_populates='battle',foreign_keys='Battleparticipations.battle_id')
    trophies = db.relationship('Trophy', back_populates='battle')
    losses_by_country = db.relationship(
        'BattleLosses',
        back_populates='battle',
        uselist=False,
        foreign_keys='BattleLosses.battle_id'
    )

    size_parties = db.relationship(
        'SizeParties', 
        back_populates='battle',
        foreign_keys='SizeParties.battle_id'
    )
    

def get_next_battle_id():
    result = db.session.query(db.func.max(Battle.id)).scalar()
    return (result or 0) + 1

class Battleparticipations(db.Model):
    __tablename__ = 'battle_participations'
    
    id = db.Column(db.Integer, primary_key=True)
    side = db.Column(db.String(20), nullable=False)
        
    # Внешние ключи (исправленные имена таблиц)
    battle_id = db.Column(db.Integer, db.ForeignKey('battles.id'), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('military_units.id'), nullable=True)
    
   # military_unit = db.relationship('MilitaryUnit', back_populates='battle_participations')
    commander_id = db.Column(db.Integer, db.ForeignKey('commanders.id'))
    
    # Отношения
    battle = db.relationship('Battle', back_populates='participations', foreign_keys=[battle_id])
    unit = db.relationship('MilitaryUnit', back_populates='battle_participations', foreign_keys=[unit_id])
    commander = db.relationship('Commander', back_populates='battle_participations')
    #losses = db.relationship('BattleLoss', back_populates='participations')


    
class Trophy(db.Model):
    __tablename__ = 'trophies'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Integer, default=1)
    
    # Внешние ключи
    battle_id = db.Column(db.Integer, db.ForeignKey('battles.id'), nullable=False)
    captor_id = db.Column(db.Integer, db.ForeignKey('military_units.id'))
    
    # Отношения
    battle = db.relationship('Battle', back_populates='trophies')
    captor = db.relationship('MilitaryUnit', backref='captured_trophies')

class Place(db.Model):
    __tablename__ = 'places'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    geom = db.Column(Geometry(geometry_type='POINT', srid=4326))
    
    # Отношения
    battles = db.relationship('Battle', back_populates='place')
    events = db.relationship('Event', back_populates='place')
    movements_from = db.relationship('UnitMovement', foreign_keys='UnitMovement.start_place_id', back_populates='start_place')
    movements_to = db.relationship('UnitMovement', foreign_keys='UnitMovement.end_place_id', back_populates='end_place')
    @property
    def latitude(self):
        """Получить широту из геометрии"""
        if self.geom is not None:
            return db.session.scalar(db.func.ST_Y(self.geom))
        return None

    @property
    def longitude(self):
        """Получить долготу из геометрии"""
        if self.geom is not None:
            return db.session.scalar(db.func.ST_X(self.geom))
        return None
    

class UnitMovement(db.Model):
    __tablename__ = 'unit_movements'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    distance_km = db.Column(db.Float)
    route_description = db.Column(db.Text)
    
    # Внешние ключи
    unit_id = db.Column(db.Integer, db.ForeignKey('military_units.id'), nullable=False)
    start_place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=False)
    end_place_id = db.Column(db.Integer, db.ForeignKey('places.id'), nullable=False)
    
    # Отношения
    unit = db.relationship('MilitaryUnit', back_populates='movements')
    start_place = db.relationship('Place', foreign_keys=[start_place_id], back_populates='movements_from')
    end_place = db.relationship('Place', foreign_keys=[end_place_id], back_populates='movements_to')

class CommanderRank(db.Model):
    __tablename__ = 'commander_ranks'
    
    id = db.Column(db.Integer, primary_key=True)  # Добавляем автоинкрементный ID
    commander_id = db.Column(db.Integer, db.ForeignKey('commanders.id'))
    rank_id = db.Column(db.Integer, db.ForeignKey('military_ranks.id'))
    date_promoted = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    
    # Явно указываем foreign_keys для отношений
    commander = db.relationship('Commander', back_populates='rank_assignments', foreign_keys=[commander_id])
    rank = db.relationship('MilitaryRank', back_populates='assignments', foreign_keys=[rank_id])

    __table_args__ = (db.UniqueConstraint('commander_id', 'rank_id', 'date_promoted', name='uq_commander_rank_date'),)

class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date)
    event = db.Column(db.String(5000))
    place_id = db.Column(db.Integer, db.ForeignKey('places.id'))
    notes = db.Column(db.String(5000))

    place = db.relationship('Place', back_populates='events')


class CommanderAssignment(db.Model):
    __tablename__ = 'commander_assignments'

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('military_units.id'), nullable=False)
    commander_id = db.Column(db.Integer, db.ForeignKey('commanders.id'), nullable=False)
    Com_start = db.Column(db.Date, nullable=False, default=date.today)
    Com_end = db.Column(db.Date, nullable=True)

    # Отношения
    unit = db.relationship(
        'MilitaryUnit',
        back_populates='commanders',
        foreign_keys=[unit_id]
    )

    commander = db.relationship(
        'Commander',
        back_populates='military_units',
        foreign_keys=[commander_id]
    )

class ConnectionType(db.Model):
    __tablename__ = 'connection_type'
    
    id = db.Column(db.Integer, primary_key=True)
    connection_type = db.Column(db.String(50), nullable=False, unique=True)
    level = db.Column(db.Integer)
    
    # Отношение к MilitaryUnit
    military_units = db.relationship('MilitaryUnit', back_populates='unit_type')
    def __repr__(self):
        return f'<ConnectionType {self.connection_type}>'
    

class SizeParties(db.Model):
    __tablename__ = 'size_parties'
    
    id = db.Column(db.Integer, primary_key=True)
    side = db.Column(db.Integer, db.ForeignKey('countries.id'))
    men = db.Column(db.Integer)
    guns = db.Column(db.Integer)
    bns = db.Column(db.Integer)  # батальоны
    coys = db.Column(db.Integer) # роты
    sqns = db.Column(db.Integer) # эскадроны
    battle_id = db.Column(db.Integer, db.ForeignKey('battles.id'))
    source_id = db.Column('sourсe_id', db.Integer, db.ForeignKey('sources.id'))
    
    # Отношения
    country = db.relationship('Country')
    battle = db.relationship(
        'Battle', 
        back_populates='size_parties',
        foreign_keys=[battle_id]
    )
    source = db.relationship('Source')

class Source(db.Model):
    __tablename__ = 'sources'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Text, nullable=False)
    author = db.Column(db.Text)
    publication_year = db.Column(db.Integer)
    archive_reference = db.Column(db.Text)
    isbn = db.Column(db.String)

class BattleDiagram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey('battles.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # или filepath
    description = db.Column(db.Text)
    is_main = db.Column(db.Boolean, default=False)
    image_path = db.Column(db.String(255))
    #created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Связь
    battle = db.relationship('Battle', backref=db.backref('diagrams', lazy=True))

from flask_wtf.file import FileField, FileAllowed, FileRequired

class DiagramForm(FlaskForm):
    image = FileField('Схема сражения', validators=[
        FileRequired(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Только изображения!')
    ])
    description = TextAreaField('Описание схемы')
    is_main = BooleanField('Основная схема')