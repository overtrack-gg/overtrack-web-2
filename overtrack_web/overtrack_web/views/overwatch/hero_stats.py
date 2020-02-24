import logging
import time
from collections import Counter, defaultdict
from typing import Optional, Dict, List, Tuple

import dataclasses
from dataclasses import dataclass
from flask import Blueprint, render_template, request
from overtrack_models.orm.overwatch_hero_stats import OverwatchHeroStats
from overtrack_models.orm.user import User

from overtrack_web.data import overwatch_data
from overtrack_web.lib.authentication import require_login
from overtrack_web.lib.context_processors import s2ts
from overtrack_web.lib.session import session

logger = logging.getLogger(__name__)

hero_stats_blueprint = Blueprint('overwatch.hero_stats', __name__)


def format_num(num: float) -> str:
    string = f"{int(num):,}"

    if "," in string:
        return string
    else:
        return f"{num:.1f}"


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

    time_played: int = 0

    games: int = 0
    wins: int = 0

    eliminations: int = 0
    objective_kills: int = 0
    objective_time: int = 0
    hero_damage_done: int = 0
    healing_done: int = 0
    deaths: int = 0
    final_blows: int = 0

    hero_specific_stats: Optional[Dict[str, int]] = None

    time_played_total: int = 0

    def base_stats(self) -> List[Tuple[str, str]]:
        wins = self.wins
        losses = self.games - self.wins
        return [
            ("PLAYTIME", s2ts(self.time_played)),
            ("PLAYRATE", f"{self.time_played / self.time_played_total:.0%}"),
            ("WINRATE", f"{self.wins / self.games:.0%}"),
            ("RECORD", f"{wins:,}-{losses:,}"),
        ]

    def general_stats(self) -> List[Tuple[str, str, str]]:
        num_10_mins = self.time_played / 600
        supp_line = [
            ("HEALING DONE", format_num(self.healing_done / num_10_mins), "/10min"),
        ] if self.healing_done > 0 else []
        return [
            ("ELIMINATIONS", format_num(self.eliminations / num_10_mins), "/10min"),
            ("OBJECTIVE KILLS", format_num(self.objective_kills / num_10_mins), "/10min"),
            ("OBJECTIVE TIME", format_num(self.objective_time / num_10_mins), "/10min"),
            ("HERO DAMAGE DONE", format_num(self.hero_damage_done / num_10_mins),
             "/10min"),
            *supp_line,
            ("DEATHS", format_num(self.deaths / num_10_mins), "/10min"),
        ]

    def specific_stats(self) -> List[Tuple[str, str, str]]:
        num_10_mins = self.time_played / 600
        output = []

        if self.hero_specific_stats is None:
            return output

        for stat, value in self.hero_specific_stats.items():
            if "best" in stat:
                small = "AVG PER GAME"
                output.append((stat.upper(), format_num(value / self.games), small))
            elif "accuracy" in stat or "percentage" in stat:
                small = "% AVG PER GAME"
                output.append((stat.upper(), format_num(value / self.games), small))
            else:
                small = "/10min"
                output.append((stat.upper(), format_num(value / num_10_mins), small))

        return sorted(output)

    @property
    def image(self) -> str:
        return f"images/overwatch/hero_icons/{self.name}.png"

    @property
    def color(self) -> str:
        try:
            return {
                "support": "#518e6e",
                "damage": "#8e5155",
                "tank": "#515d8e",
                #
                "ana": "#718ab3",
                # "ashe": "",
                # "baptiste": "",
                "bastion": "#7c8f7b",
                "brigitte": "#be736e",
                "doomfist": "#815049",
                "dva": "#ed93c7",
                "genji": "#97ef43",
                # "hammond": "",
                "hanzo": "#b9b48a",
                "junkrat": "#ecbd53",
                "lucio": "#85c952",
                "mccree": "#ae595c",
                "mei": "#6faced",
                "mercy": "#ebe8bb",
                "moira": "#803c51",
                "orisa": "#468c43",
                "pharah": "#3e7dca",
                "reaper": "#7d3e51",
                "reinhardt": "#929da3",
                "roadhog": "#b68c52",
                # "sigma": "",
                "soldier": "#697794",
                "sombra": "#7359ba",
                "symmetra": "#8ebccc",
                "torbjorn": "#c0726e",
                "tracer": "#d79342",
                "widowmaker": "#9e6aa8",
                "winston": "#a2a6bf",
                "zarya": "#e77eb6",
                "zenyatta": "#ede582",
            }[self.name]
        except KeyError:
            return "#5d518e"

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
        return "#000000" if l > 0.179 else "#ffffff"

    @classmethod
    def from_db_stat(cls, stat: OverwatchHeroStats, include_hero_stats: bool, endgame_only: bool) -> 'OverwatchCollectedHeroStats':
        if endgame_only:
            assert stat.from_endgame
        return cls(
            include_hero_stats=include_hero_stats,
            endgame_only=endgame_only,

            time_played=int(stat.time_played),

            games=1,
            wins=stat.game_result in ['VICTORY', 'WIN'],

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

            time_played=self.time_played + other.time_played,

            games=self.games + other.games,
            wins=self.wins + other.wins,

            eliminations=self.eliminations + other.eliminations,
            objective_kills=self.objective_kills + other.objective_kills,
            objective_time=self.objective_time + other.objective_time,
            hero_damage_done=self.hero_damage_done + other.hero_damage_done,
            healing_done=self.healing_done + other.healing_done,
            deaths=self.deaths + other.deaths,
            final_blows=(self.final_blows or 0) + (other.final_blows or 0),

            hero_specific_stats=hero_specific_stats,
        )


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
    complete_only = request.args.get('complete_only', 'false') == 'true'

    condition = OverwatchHeroStats.season == season_id

    if account:
        condition &= OverwatchHeroStats.account == account

    # Only include custom stats if mode is explicitly custom
    if mode == 'custom':
        condition &= OverwatchHeroStats.custom_game == True
    else:
        condition &= OverwatchHeroStats.custom_game == False
        if mode == 'all':
            pass
        elif mode == 'competitive':
            condition &= OverwatchHeroStats.competitive == True
        elif mode == 'quickplay':
            condition &= OverwatchHeroStats.competitive == False
        else:
            return 'Unknown mode', 400

    if complete_only:
        condition &= OverwatchHeroStats.from_endgame == True

    seasons = [
        s for i, s in overwatch_data.seasons.items() if i in user.overwatch_seasons
    ]
    seasons.sort(key=lambda s: s.start, reverse=True)

    accounts = Counter()  # FIXME: account lists will not be populated when viewing a single account

    all_stats = OverwatchCollectedHeroStats(include_hero_stats=False,
                                            endgame_only=complete_only)
    hero_stats = defaultdict(lambda: OverwatchCollectedHeroStats(include_hero_stats=True,
                                                                 endgame_only=complete_only))
    role_stats = defaultdict(lambda: OverwatchCollectedHeroStats(include_hero_stats=False,
                                                                 endgame_only=complete_only))

    logger.info(
        f'Fetching hero stats for user_id {user.user_id} for season {season_id} with filter {condition}')
    query = OverwatchHeroStats.user_id_timestamp_index.query(
        user.user_id,
        OverwatchHeroStats.timestamp.between(overwatch_data.seasons[season_id].start,
                                             overwatch_data.seasons[season_id].end),
        condition,
    )
    t0 = time.perf_counter()
    for stat in query:
        if stat.hero == 'all heroes':
            all_stats += stat
        else:
            hero_stats[stat.hero] += stat
            role_stats[overwatch_data.heroes[stat.hero].role] += stat

        accounts[stat.account] += 1
    logger.info(
        f'Fetched {query.total_count} items in {(time.perf_counter() - t0) * 1000:.2f}ms')

    for name, stat in hero_stats.items():
        stat.name = name

    for name, stat in role_stats.items():
        stat.name = name

    hero_stats_by_playtime = sorted(
        hero_stats.values(),
        key=lambda h: h.time_played,
        reverse=True,
    )
    hero_playtime_total = sum(x.time_played for x in hero_stats_by_playtime)
    for x in hero_stats_by_playtime:
        x.time_played_total = hero_playtime_total

    role_stats = sorted(
        role_stats.values(),
        key=lambda r: r.time_played,
        reverse=True,
    )
    role_playtime_total = sum(x.time_played for x in role_stats)
    for x in role_stats:
        x.time_played_total = role_playtime_total

    href_season = f"season={season_id}" if has_season else ""
    href_account = f"account={account}" if has_account else ""
    href_mode = f"mode={mode}" if has_mode else ""
    href_complete_only = f"complete_only={str(complete_only).lower()}" if has_complete_only else ""

    def href_change_season(new_season):
        return "?" + "&".join(x for x in [
            f"season={new_season}",
            href_account,
            href_mode,
            href_complete_only
        ] if x)

    def href_change_account(new_account):
        if new_account == 'All Accounts':
            account_line = ''
        else:
            account_line = f"account={new_account}"

        return "?" + "&".join(x for x in [
            href_season,
            account_line,
            href_mode,
            href_complete_only
        ] if x)

    def href_change_mode(new_mode):
        return "?" + "&".join(x for x in [
            href_season,
            href_account,
            f"mode={new_mode.lower()}",
            href_complete_only
        ] if x)

    def href_change_complete_only(old_complete_only):
        new_complete_only = not old_complete_only
        return "?" + "&".join(x for x in [
            href_season,
            href_account,
            href_mode,
            f"complete_only={str(new_complete_only).lower()}",
        ] if x)

    accounts_list = ['All Accounts', *accounts.keys()]

    return render_template(
        'overwatch/hero_stats/hero_stats.html',
        seasons=seasons,
        current_season=overwatch_data.seasons[season_id],
        accounts=accounts_list,
        current_account=account or "All Accounts",
        modes=['All', 'Competitive', 'Quickplay'],
        current_mode=mode,
        complete_only=complete_only,
        change_func={
            "season": href_change_season,
            "account": href_change_account,
            "mode": href_change_mode,
            "complete": href_change_complete_only
        },
        stats=all_stats,
        roles=role_stats,
        heroes=hero_stats_by_playtime
    )


@hero_stats_blueprint.route('/')
@require_login
def results():
    return render_results(session.user)
