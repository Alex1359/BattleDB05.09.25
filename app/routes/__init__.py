from .commanders import bp as commanders_bp
from .units import bp as units_bp
from .battles import bp as battles_bp
from .movements import bp as movements_bp
from .events import events_bp

def init_app(app):
    app.register_blueprint(commanders_bp)
    app.register_blueprint(units_bp)
    app.register_blueprint(battles_bp)
    app.register_blueprint(movements_bp)
    app.register_blueprint(events_bp, url_prefix='/events')