from datetime import date
from app.models import Commander, CommanderRank, MilitaryRank, db

class CommanderService:
    @staticmethod
    def add_rank_to_commander(commander_id, rank_id, promotion_date=None):
        """Добавляет звание командиру с указанной датой"""
        promotion_date = promotion_date or date.today()
        
        assignment = CommanderRank(
            commander_id=commander_id,
            rank_id=rank_id,
            date_promoted=promotion_date
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment

    @staticmethod
    def get_commander_ranks_history(commander_id):
        """Получить историю званий с информацией о званиях"""
        return db.session.query(CommanderRank).\
            join(MilitaryRank).\
            filter(CommanderRank.commander_id == commander_id).\
            order_by(CommanderRank.date_promoted.desc()).\
            all()