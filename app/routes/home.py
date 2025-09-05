from flask import render_template, Blueprint

home_bp = Blueprint('home', __name__)

# Главная страница (корневой URL)
@home_bp.route('/')
def index():
    return render_template('home.html')

# Явный роут для /home/
@home_bp.route('/home')
@home_bp.route('/home/')
def home():
    return render_template('home.html')  # Можно использовать тот же шаблон