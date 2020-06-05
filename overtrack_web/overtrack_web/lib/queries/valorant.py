import logging

import os

try:
    from overtrack_models.queries.valorant.winrates import MapAgentWinrates
    from overtrack.valorant.collect.relational import queries

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine((
        f'postgresql://'
        f'overtrack'
        f':'
        f'{os.environ["PSQL_PASSWORD"]}'
        f'@'
        f'{os.environ["PSQL_HOST"]}'
        f':'
        f'{os.environ["PSQL_PORT"]}'
        f'/overtrack'
    ),
        echo=True,
        executemany_mode='batch',
    )
    db_session = sessionmaker(bind=engine)()
except:
    logging.exception('Failed to connect to database - no db session created')
    db_session = None


def get_winrates(user_id: int) -> MapAgentWinrates:
    return queries.agent_map_winrates(db_session, user_id, game_version_atleast='01.00.0')


def get_average_winrates() -> MapAgentWinrates:
    return queries.agent_map_winrates(db_session, None, game_version_atleast='01.00.0')
