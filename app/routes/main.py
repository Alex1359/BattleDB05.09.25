from flask import Blueprint, redirect, render_template, request, url_for

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    query = request.args.get('q', '')
    if query:
        # Реализуйте поиск по всем разделам или просто перенаправьте
        return redirect(url_for('commanders.list_commanders', q=query))
    return render_template('index.html')