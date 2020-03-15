import logging
from collections import Counter, defaultdict
from pprint import pprint
from typing import Optional, Dict, List, Tuple

import time
from dataclasses import dataclass
from flask import Blueprint, render_template, request

from overtrack_models.orm.overwatch_game_summary import OverwatchGameSummary
from overtrack_models.orm.overwatch_hero_stats import OverwatchHeroStats
from overtrack_models.orm.user import User
from overtrack_web.data import overwatch_data
from overtrack_web.data.overwatch_data import hero_colors
from overtrack_web.lib.authentication import require_login
from overtrack_web.lib.context_processors import s2ts
from overtrack_web.lib.session import session

logger = logging.getLogger(__name__)

hero_stats_blueprint = Blueprint('overwatch.hero_stats', __name__)


def format_num(num: float) -> str:
    string = f'{int(num):,}'

    if ',' in string:
        return string
    else:
        return f'{num:.1f}'


@hero_stats_blueprint.context_processor
def context_processor():
    return {
        'game_name': 'overwatch',
    }


@dataclass
class OverwatchCollectedHeroStats:
    include_hero_stats: bool
    endgame_only: bool

    name: str = None

    games: float = 0
    wins: float = 0
    time_selected: float = 0

    games_with_stats: int = 0
    wins_with_stats: int = 0
    time_active: float = 0
    eliminations: int = 0
    objective_kills: int = 0
    objective_time: int = 0
    hero_damage_done: int = 0
    healing_done: int = 0
    deaths: int = 0
    final_blows: int = 0

    hero_specific_stats: Optional[Dict[str, int]] = None

    time_active_total: int = 0

    def base_stats(self) -> List[Tuple[str, str]]:
        wins = self.wins
        losses = self.games - self.wins
        return [
            ('PLAYTIME', s2ts(self.time_selected)),
            ('PLAYRATE', f'{self.time_selected / self.time_active_total:.0%}'),
            ('WINRATE', f'{self.wins / self.games:.0%}'),
            ('RECORD', f'{int(wins):,}-{int(losses):,}'),
        ]

    def general_stats(self) -> List[Tuple[str, str, str]]:
        print(self)
        num_10_mins = self.time_active / 600
        supp_line = [
            ('HEALING DONE', format_num(self.healing_done / num_10_mins), '/10min'),
        ] if self.healing_done > 0 else []
        return [
            ('ELIMINATIONS', format_num(self.eliminations / num_10_mins), '/10min'),
            ('OBJECTIVE KILLS', format_num(self.objective_kills / num_10_mins), '/10min'),
            ('OBJECTIVE TIME', format_num(self.objective_time / num_10_mins), '/10min'),
            ('HERO DAMAGE DONE', format_num(self.hero_damage_done / num_10_mins),
             '/10min'),
            *supp_line,
            ('DEATHS', format_num(self.deaths / num_10_mins), '/10min'),
        ]

    def specific_stats(self) -> List[Tuple[str, str, str]]:
        num_10_mins = self.time_active / 600
        output = []

        if self.hero_specific_stats is None:
            return output

        for stat, value in self.hero_specific_stats.items():
            if 'best' in stat:
                small = '(AVG / GAME)'
                output.append((stat.upper(), format_num(value / self.games), small))
            elif 'accuracy' in stat or 'percentage' in stat or 'average' in stat:
                small = '%'
                output.append((stat.upper(), format_num(value / self.games), small))
            else:
                small = '/10min'
                output.append((stat.upper(), format_num(value / num_10_mins), small))

        return sorted(output)

    @property
    def image(self) -> str:
        return f'images/overwatch/hero_icons/{self.name}.png'

    @property
    def color(self) -> str:
        colors = {
            'support': '#36778f',
            'damage': '#8f406d',
            'tank': '#8f6f29',
        }
        colors.update(hero_colors)

        try:
            return colors[self.name]
        except KeyError:
            return '#5d518e'

    @property
    def text_color(self) -> str:
        # https://stackoverflow.com/a/3943023
        rgb = [
            int(h, 16) / 255.0
            for h in
            (self.color[1:3], self.color[3:5], self.color[5:7])
        ]

        for i in range(3):
            if rgb[i] <= 0.03928:
                rgb[i] /= 12.92
            else:
                rgb[i] = ((rgb[i] + 0.055) / 1.055) ** 2.4

        r, g, b = rgb
        l = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return '#000000' if l > 0.179 else '#ffffff'

    @classmethod
    def from_db_stat(cls, stat: OverwatchHeroStats, include_hero_stats: bool, endgame_only: bool) -> 'OverwatchCollectedHeroStats':
        if endgame_only:
            assert stat.from_endgame
        return cls(
            include_hero_stats=include_hero_stats,
            endgame_only=endgame_only,

            time_active=stat.time_played,
            games_with_stats=1,
            wins_with_stats=stat.game_result in ['WIN', 'VICTORY'],
            eliminations=stat.eliminations,
            objective_kills=stat.objective_kills,
            objective_time=stat.objective_time,
            hero_damage_done=stat.hero_damage_done,
            healing_done=stat.healing_done,
            deaths=stat.deaths,
            final_blows=stat.final_blows,

            hero_specific_stats=stat.hero_specific_stats if include_hero_stats else None,
        )

    def __add__(self, other) -> 'OverwatchCollectedHeroStats':
        if isinstance(other, OverwatchHeroStats):
            other = self.from_db_stat(other, self.include_hero_stats, self.endgame_only)
        if not isinstance(other, OverwatchCollectedHeroStats):
            raise ValueError(f'Cannot add {self.__class__.__name__} to {other.__class__.__name__}')

        if self.include_hero_stats:
            if self.hero_specific_stats and other.hero_specific_stats:
                hero_specific_stats = {
                    k: self.hero_specific_stats.get(k, 0) + other.hero_specific_stats.get(k, 0)
                    for k in self.hero_specific_stats
                }
            else:
                hero_specific_stats = self.hero_specific_stats or other.hero_specific_stats
        else:
            hero_specific_stats = None

        return OverwatchCollectedHeroStats(
            include_hero_stats=self.include_hero_stats,
            endgame_only=self.endgame_only or other.endgame_only,

            name=self.name or other.name,

            time_active=self.time_active + other.time_active,
            games_with_stats=self.games_with_stats + other.games_with_stats,
            wins_with_stats=self.wins_with_stats + other.wins_with_stats,
            eliminations=self.eliminations + other.eliminations,
            objective_kills=self.objective_kills + other.objective_kills,
            objective_time=self.objective_time + other.objective_time,
            hero_damage_done=self.hero_damage_done + other.hero_damage_done,
            healing_done=self.healing_done + other.healing_done,
            deaths=self.deaths + other.deaths,
            final_blows=(self.final_blows or 0) + (other.final_blows or 0),

            hero_specific_stats=hero_specific_stats,
        )

    def add_base_stats(self, game: OverwatchGameSummary, role: bool = False, hero: str = None):
        if role:
            duration = game.duration
            self.wins += int(game.result in ['WIN', 'VICTORY'])
            self.games += 1
        else:
            self.wins += int(game.result in ['WIN', 'VICTORY']) * dict(game.heroes_played)[hero]
            self.games += dict(game.heroes_played)[hero]
            duration = game.duration * dict(game.heroes_played)[hero]
        self.time_selected += duration


def render_results(user: User):
    if user.overwatch_last_season is None:
        return render_template('client.html', no_games_alert=True)

    has_season = 'season' in request.args
    has_account = 'account' in request.args
    has_mode = 'mode' in request.args
    has_complete_only = 'complete_only' in request.args

    season_id = int(request.args.get('season', user.overwatch_last_season))
    account = request.args.get('account', None)
    mode = request.args.get('mode', 'competitive')
    complete_only = request.args.get('complete_only', 'true') == 'true'

    games_condition = (OverwatchGameSummary.season == season_id) & (OverwatchGameSummary.role.is_in('tank', 'damage', 'support'))
    stats_condition = (OverwatchHeroStats.season == season_id) & (OverwatchHeroStats.hero != 'all heroes')

    if account:
        # Don't filter games_condition, since we need it to know the player names
        stats_condition &= OverwatchHeroStats.account == account

    # Only include custom stats if mode is explicitly custom
    if mode == 'custom':
        games_condition &= OverwatchGameSummary.game_type.is_in('quickplay', 'competitive')
        stats_condition &= OverwatchHeroStats.custom_game == True
    else:
        stats_condition &= OverwatchHeroStats.custom_game == False
        if mode == 'all':
            pass
        elif mode == 'competitive':
            games_condition &= OverwatchGameSummary.game_type == 'competitive'
            stats_condition &= OverwatchHeroStats.competitive == True
        elif mode == 'quickplay':
            games_condition &= OverwatchGameSummary.game_type == 'quickplay'
            stats_condition &= OverwatchHeroStats.competitive == False
        else:
            return 'Unknown mode', 400

    if complete_only:
        stats_condition &= OverwatchHeroStats.from_endgame == True

    seasons = [
        s for i, s in overwatch_data.seasons.items() if i in user.overwatch_seasons
    ]
    seasons.sort(key=lambda s: s.start, reverse=True)

    hero_stats = defaultdict(lambda: OverwatchCollectedHeroStats(include_hero_stats=True, endgame_only=complete_only))

    logger.info(f'Fetching hero stats for user_id {user.user_id} for season {season_id} with filter {stats_condition}')
    query = OverwatchHeroStats.user_id_timestamp_index.query(
        user.user_id,
        OverwatchHeroStats.timestamp.between(
            overwatch_data.seasons[season_id].start,
            overwatch_data.seasons[season_id].end
        ),
        stats_condition,
    )
    t0 = time.perf_counter()
    for stat in query:
        hero_stats[stat.hero] += stat
    logger.info(f'Fetched {query.total_count} items in {(time.perf_counter() - t0) * 1000:.2f}ms')
    pprint(hero_stats)

    accounts = Counter()  # FIXME: account lists will not be populated when viewing a single account
    role_stats = defaultdict(lambda: OverwatchCollectedHeroStats(include_hero_stats=False, endgame_only=complete_only))

    logger.info(f'Fetching games for user_id {user.user_id} for season {season_id} with filter {games_condition}')
    t0 = time.perf_counter()
    query = OverwatchGameSummary.user_id_time_index.query(
        user.user_id,
        OverwatchGameSummary.time.between(
            overwatch_data.seasons[season_id].start,
            overwatch_data.seasons[season_id].end
        ),
        games_condition,
        attributes_to_get=[
            OverwatchGameSummary.role,
            OverwatchGameSummary.result,
            OverwatchGameSummary.duration,
            OverwatchGameSummary.heroes_played,
            OverwatchGameSummary.player_name,
        ]
    )
    for g in query:
        if not account or g.player_name == account:
            role_stats[g.role].add_base_stats(g, role=True)
            for h, f in g.heroes_played:
                if f > 0.25:
                    hero_stats[h].add_base_stats(g, hero=h)
        accounts[g.player_name] += 1
    logger.info(f'Fetched {query.total_count} items in {(time.perf_counter() - t0) * 1000:.2f}ms')
    pprint(role_stats)

    for name, stat in hero_stats.items():
        stat.name = name

    for name, stat in role_stats.items():
        stat.name = name

    hero_stats_by_playtime = sorted(
        hero_stats.values(),
        key=lambda h: h.time_selected,
        reverse=True,
    )
    time_in_game_total = sum(x.time_selected for x in hero_stats_by_playtime)
    for x in hero_stats_by_playtime:
        x.time_active_total = time_in_game_total

    role_stats = sorted(
        role_stats.values(),
        key=lambda r: r.time_selected,
        reverse=True,
    )
    role_time_in_game_total = sum(x.time_selected for x in role_stats)
    for x in role_stats:
        x.time_active_total = role_time_in_game_total

    href_season = f'season={season_id}' if has_season else ''
    href_account = f'account={account}' if has_account else ''
    href_mode = f'mode={mode}' if has_mode else ''
    href_complete_only = f'complete_only={str(complete_only).lower()}' if has_complete_only else ''

    def href_change_season(new_season):
        return '?' + '&'.join(x for x in [
            f'season={new_season}',
            href_account,
            href_mode,
            href_complete_only
        ] if x)

    def href_change_account(new_account):
        if new_account == 'All Accounts':
            account_line = ''
        else:
            account_line = f'account={new_account}'

        return '?' + '&'.join(x for x in [
            href_season,
            account_line,
            href_mode,
            href_complete_only
        ] if x)

    def href_change_mode(new_mode):
        return '?' + '&'.join(x for x in [
            href_season,
            href_account,
            f'mode={new_mode.lower()}',
            href_complete_only
        ] if x)

    def href_change_complete_only(old_complete_only):
        new_complete_only = not old_complete_only
        return '?' + '&'.join(x for x in [
            href_season,
            href_account,
            href_mode,
            f'complete_only={str(new_complete_only).lower()}',
        ] if x)

    accounts_list = ['All Accounts', *accounts.keys()]

    return render_template(
        'overwatch/hero_stats/performance_stats.html',
        seasons=seasons,
        current_season=overwatch_data.seasons[season_id],
        accounts=accounts_list,
        current_account=account or 'All Accounts',
        modes=['All', 'Competitive', 'Quickplay'],
        current_mode=mode,
        complete_only=complete_only,
        change_func={
            'season': href_change_season,
            'account': href_change_account,
            'mode': href_change_mode,
            'complete': href_change_complete_only
        },
        roles=role_stats,
        heroes=hero_stats_by_playtime
    )


@hero_stats_blueprint.route('/')
@require_login
def results():
    return render_results(session.user)
