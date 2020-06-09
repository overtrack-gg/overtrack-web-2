from contextlib import contextmanager
from typing import ContextManager

import logging

import os

try:
    from overtrack_models.queries.valorant.winrates import MapAgentWinrates
    from overtrack.valorant.relational import queries

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker, Session

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

    session_maker = sessionmaker(bind=engine)

    @contextmanager
    def db_session() -> ContextManager[Session]:
        sess = session_maker()
        try:
            yield sess
            sess.commit()
        except:
            sess.rollback()
            raise
        finally:
            sess.close()

except:
    logging.exception('Failed to connect to database - no db session created')
    db_session = None


def get_winrates(user_id: int) -> MapAgentWinrates:
    with db_session() as sess:
        return queries.agent_map_winrates(sess, user_id, game_version_atleast='01.00.0')


def get_average_winrates() -> MapAgentWinrates:
    with db_session() as sess:
        return queries.agent_map_winrates(sess, None, game_version_atleast='01.00.0')
