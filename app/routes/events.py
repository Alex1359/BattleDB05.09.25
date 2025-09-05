from flask import Blueprint, render_template
from sqlalchemy import func
from app.models import Event, Place
from datetime import datetime
from dateutil import parser
import json
from app import db


events_bp = Blueprint('events', __name__)

@events_bp.route('/events')
def list_events():
    # Добавьте order_by(Event.date)
    events_query = db.session.query(
        Event.id,
        Event.event,
        Event.date,
        Place.name.label('place_name'),
        func.ST_AsGeoJSON(Place.geom).label('geom_json')
    ).join(Place).order_by(Event.date).all()  # ← добавлено .order_by(Event.date)

    events_data = []
    for event in events_query:
        timestamp = 0
        if event.date:
            try:
                dt = parser.parse(event.date.strftime('%Y-%m-%d'))
                timestamp = (dt - datetime(1970, 1, 1)).total_seconds()
            except Exception as e:
                print(f"Error processing date for event {event.id}: {str(e)}")
                timestamp = 0

        events_data.append({
            'id': event.id,
            'event': event.event,
            'date': event.date.strftime('%Y-%m-%d') if event.date else None,
            'timestamp': int(timestamp),
            'place_name': event.place_name,
            'geom': json.loads(event.geom_json) if event.geom_json else None
        })

    return render_template('events/list.html', events=events_data)