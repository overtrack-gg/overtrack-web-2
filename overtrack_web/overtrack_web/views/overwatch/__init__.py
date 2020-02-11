from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary


OLDEST_SUPPORTED_GAME_VERSION = '2.1.0'


def sr_change(game: OverwatchGameSummary) -> str:
    if game.rank == 'placement':
        return '-'
    elif game.start_sr and game.end_sr:
        if game.start_sr == game.end_sr:
            return '0'
        else:
            return f'{game.end_sr - game.start_sr:+}'
    else:
        return '?'
