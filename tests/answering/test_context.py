from ffassistant.answering.context import render_context
from ffassistant.answering.models import PlayerInputs, ResolvedContext, SourceResult
from ffassistant.answering.sources.defense import DefenseData, DefenseRow
from ffassistant.answering.sources.injuries import InjuryData, InjuryEntry
from ffassistant.answering.sources.recent_stats import GameLine, RecentStatsData
from ffassistant.answering.sources.schedule import ScheduleData, ScheduleWeek
from ffassistant.resolution.models import RejectedMention, ValidatedRequest, ValidPlayer


def _validated(
    players: list[PlayerInputs],
    mentions: dict[str, str] | None = None,
    rejected: list[RejectedMention] | None = None,
) -> ValidatedRequest:
    mentions = mentions or {}
    return ValidatedRequest(
        raw_prompt="Lamb or Jefferson?",
        season=2026,
        week=7,
        scoring_format="PPR",
        players=[
            ValidPlayer(
                mention=mentions.get(p.ctx.player_name, p.ctx.player_name),
                player_id=p.ctx.player_id,
                full_name=p.ctx.player_name,
                position=p.ctx.position,
            )
            for p in players
        ],
        rejected=rejected or [],
    )


def _render(
    players: list[PlayerInputs],
    mentions: dict[str, str] | None = None,
    rejected: list[RejectedMention] | None = None,
) -> str:
    return render_context(_validated(players, mentions, rejected), players)


def _ctx(
    name: str,
    team: str,
    scoring_format: str = "PPR",
    position: str = "WR",
    roster_status: str = "ACT",
) -> ResolvedContext:
    return ResolvedContext(
        player_id=f"id-{name}",
        player_name=name,
        team=team,
        position=position,
        roster_status=roster_status,
        season=2026,
        week=7,
        scoring_format=scoring_format,
    )


def _ok_result() -> SourceResult[RecentStatsData]:
    games = [
        GameLine(
            week=1,
            opponent="NYG",
            stats={"receptions": 6, "fantasy_points": 12.4, "fantasy_points_ppr": 18.4},
        ),
        GameLine(
            week=2,
            opponent="PHI",
            stats={"receptions": 4, "fantasy_points": 5.0, "fantasy_points_ppr": 9.0},
        ),
    ]
    return SourceResult(
        source="recent_stats",
        status="ok",
        as_of="Week 7",
        data=RecentStatsData(position="WR", games=games),
    )


def _schedule_result(*replacements: ScheduleWeek) -> SourceResult[ScheduleData]:
    weeks = {
        1: ScheduleWeek(week=1, opponent="NYG", home=True, played=True),
        2: ScheduleWeek(week=2, opponent="PHI", home=False, played=True),
        3: ScheduleWeek(week=3, opponent="CHI", home=True, played=True),
        4: ScheduleWeek(week=4, opponent="MIA", home=False, played=True),
        5: ScheduleWeek(week=5, opponent="GB", home=True, played=True),
        6: ScheduleWeek(week=6, opponent=None, home=None, played=False),
        7: ScheduleWeek(week=7, opponent="IND", home=True, played=False),
    }
    for week in replacements:
        weeks[week.week] = week
    return SourceResult(
        source="schedule",
        status="ok",
        as_of="Week 7",
        data=ScheduleData(team="DAL", weeks=[weeks[w] for w in sorted(weeks)]),
    )


def _defense_result(rows: list[DefenseRow] | None = None) -> SourceResult[DefenseData]:
    if rows is None:
        rows = [
            DefenseRow(team="IND", games=6, standard_pg=24.0, ppr_pg=34.0),
            DefenseRow(team="BAL", games=5, standard_pg=25.0, ppr_pg=40.0),
            DefenseRow(team="SF", games=6, standard_pg=26.0, ppr_pg=30.0),
            DefenseRow(team="NYG", games=6, standard_pg=17.0, ppr_pg=20.0),
        ]
    return SourceResult(
        source="defense", status="ok", as_of="Week 7", data=DefenseData(position="WR", rows=rows)
    )


def _injury_result(entry: InjuryEntry | None = None) -> SourceResult[InjuryData]:
    return SourceResult(
        source="injuries", status="ok", as_of="Week 7", data=InjuryData(week=7, entry=entry)
    )


def _inputs(
    ctx: ResolvedContext,
    stats: SourceResult[RecentStatsData],
    sched: SourceResult[ScheduleData] | None = None,
    defense: SourceResult[DefenseData] | None = None,
    injuries: SourceResult[InjuryData] | None = None,
) -> PlayerInputs:
    return PlayerInputs(
        ctx=ctx,
        recent_stats=stats,
        schedule=sched if sched is not None else _schedule_result(),
        defense=defense if defense is not None else _defense_result(),
        injuries=injuries if injuries is not None else _injury_result(),
    )


def _kicker_result() -> SourceResult[RecentStatsData]:
    games = [
        GameLine(
            week=1,
            opponent="NYG",
            stats={"fg_made": 3, "fg_att": 4, "pat_made": 2, "fantasy_points": 0.0, "fantasy_points_ppr": 0.0},
        ),
    ]
    return SourceResult(
        source="recent_stats",
        status="ok",
        as_of="Week 7",
        data=RecentStatsData(position="K", games=games),
    )


def _line_with(context: str, needle: str) -> str:
    matches = [line for line in context.splitlines() if needle in line]
    assert len(matches) == 1, f"expected one line containing {needle!r}, got {matches}"
    return matches[0]


def test_render_context_includes_request_header():
    context = _render([])

    assert "Lamb or Jefferson?" in context
    assert "7" in _line_with(context, "Week")
    assert "PPR" in _line_with(context, "Scoring format")


def test_render_context_ok_renders_one_row_per_game():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    week_1 = _line_with(context, "NYG")
    week_2 = _line_with(context, "PHI")
    assert "DAL" in _line_with(context, "CeeDee Lamb")
    assert "Week 1" in week_1 and "receptions=6" in week_1
    assert "fantasy_points (PPR)=18.4" in week_1
    assert "Week 2" in week_2 and "receptions=4" in week_2


def test_render_context_uses_standard_points_for_standard_scoring():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL", "Standard"), _ok_result())])

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Standard)=12.4" in week_1
    assert "18.4" not in week_1


def test_render_context_derives_half_ppr_points():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL", "Half-PPR"), _ok_result())])

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Half-PPR)=15.4" in week_1
    assert "12.4" not in week_1 and "18.4" not in week_1


def test_render_context_empty_without_schedule_says_no_games():
    empty = SourceResult(source="recent_stats", status="empty", as_of="Week 7")
    no_schedule = SourceResult(source="schedule", status="empty", as_of="Week 7")

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), empty, no_schedule)])

    line = _line_with(context.lower(), "no games")
    assert "DAL" in _line_with(context, "CeeDee Lamb")
    assert "week 7" in line


def test_render_context_error_includes_error_string():
    error = SourceResult(
        source="recent_stats", status="error", as_of="Week 7", error="HTTPError: 503"
    )

    context = _render([_inputs(_ctx("Justin Jefferson", "MIN"), error)])

    assert "MIN" in _line_with(context, "Justin Jefferson")
    assert "HTTPError: 503" in context


def test_render_context_keeps_every_player():
    empty = SourceResult(source="recent_stats", status="empty", as_of="Week 7")
    error = SourceResult(source="recent_stats", status="error", as_of="Week 7", error="boom")

    context = _render(
        [
            _inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result()),
            _inputs(_ctx("Justin Jefferson", "MIN"), empty),
            _inputs(_ctx("Ja'Marr Chase", "CIN"), error),
        ]
    )

    for name, team in [("CeeDee Lamb", "DAL"), ("Justin Jefferson", "MIN"), ("Ja'Marr Chase", "CIN")]:
        assert team in _line_with(context, name)


def test_target_week_home_game():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    assert "Week 7: vs IND" in context.splitlines()


def test_target_week_away_game():
    sched = _schedule_result(ScheduleWeek(week=7, opponent="BAL", home=False, played=False))

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched)])

    assert "Week 7: @ BAL" in context.splitlines()


def test_target_week_bye():
    sched = _schedule_result(ScheduleWeek(week=7, opponent=None, home=None, played=False))

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched)])

    assert "Week 7: BYE" in context.splitlines()


def test_target_week_line_follows_header_and_injury_line():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    lines = context.splitlines()
    header = lines.index("## CeeDee Lamb (DAL)")
    assert lines[header + 1] == "Not on the Week 7 injury report"
    assert lines[header + 2] == "Week 7: vs IND"


def test_past_bye_week_line():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    assert "Week 6: BYE" in context.splitlines()


def test_played_week_without_stat_row_is_did_not_play():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    assert "Week 4 @ MIA: did not play" in context.splitlines()


def test_unplayed_past_week_is_stats_pending():
    sched = _schedule_result(ScheduleWeek(week=6, opponent="SF", home=True, played=False))

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched)])

    assert "Week 6 vs SF: game not yet played, stats pending" in context.splitlines()


def test_one_line_per_past_week_in_order():
    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    week_lines = [line for line in context.splitlines() if line.startswith("Week ") and ":" in line]
    assert [line.split(":")[0].split()[1] for line in week_lines] == ["7", "1", "2", "3", "4", "5", "6"]


def test_stats_error_with_schedule_keeps_schedule_lines():
    error = SourceResult(
        source="recent_stats", status="error", as_of="Week 7", error="HTTPError: 503"
    )

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), error)])

    lines = context.splitlines()
    assert "recent_stats failed to load: HTTPError: 503" in lines
    assert "Week 6: BYE" in lines
    assert "Week 4 @ MIA: stats unavailable" in lines
    assert not any("did not play" in line for line in lines)


def test_schedule_error_falls_back_to_stats_only():
    sched_error = SourceResult(
        source="schedule", status="error", as_of="Week 7", error="HTTPError: 502"
    )

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched_error)])

    lines = context.splitlines()
    assert "HTTPError: 502" in _line_with(context, "schedule")
    assert "fantasy_points (PPR)=18.4" in _line_with(context, "NYG")
    assert "receptions=4" in _line_with(context, "PHI")
    assert not any("BYE" in line or "did not play" in line for line in lines)


def test_kicker_renders_raw_stats_without_points():
    context = _render([_inputs(_ctx("Brandon Aubrey", "DAL", position="K"), _kicker_result())])

    week_1 = _line_with(context, "NYG")
    assert "fg_made=3" in week_1 and "fg_att=4" in week_1 and "pat_made=2" in week_1
    assert "fantasy_points" not in week_1
    assert (
        "fantasy points unavailable for kickers (kicking is not scored in the source data)"
        in context.splitlines()
    )


def _matchup_context(
    scoring_format: str = "PPR",
    opponent: str | None = "IND",
    defense: SourceResult[DefenseData] | None = None,
) -> list[str]:
    sched = _schedule_result(ScheduleWeek(week=7, opponent=opponent, home=True, played=False))
    ctx = _ctx("CeeDee Lamb", "DAL", scoring_format)
    return _render([_inputs(ctx, _ok_result(), sched, defense)]).splitlines()


def _matchup_line(lines: list[str]) -> str:
    matches = [line for line in lines if line.startswith("Matchup")]
    assert len(matches) == 1, f"expected one matchup line, got {matches}"
    return matches[0]


def test_matchup_line_follows_target_week_then_caveat():
    lines = _matchup_context()

    target = lines.index("Week 7: vs IND")
    assert lines[target + 1] == (
        "Matchup: IND has allowed 34.0 PPR points per game to WRs "
        "(rank 2 of 4, 1 = most allowed, league avg 31.0, 6 games)"
    )
    assert lines[target + 2] == (
        "Points allowed is a small early-season sample and is not adjusted for opponents faced."
    )


def test_matchup_line_standard():
    assert _matchup_line(_matchup_context("Standard")) == (
        "Matchup: IND has allowed 24.0 Standard points per game to WRs "
        "(rank 3 of 4, 1 = most allowed, league avg 23.0, 6 games)"
    )


def test_matchup_line_half_ppr_ranks_on_midpoint():
    assert _matchup_line(_matchup_context("Half-PPR")) == (
        "Matchup: IND has allowed 29.0 Half-PPR points per game to WRs "
        "(rank 2 of 4, 1 = most allowed, league avg 27.0, 6 games)"
    )


def test_matchup_rank_one_is_most_allowed():
    assert "(rank 1 of 4," in _matchup_line(_matchup_context(opponent="BAL"))
    assert "(rank 4 of 4," in _matchup_line(_matchup_context(opponent="NYG"))


def test_matchup_ties_share_a_rank():
    defense = _defense_result(
        [
            DefenseRow(team="IND", games=6, standard_pg=20.0, ppr_pg=34.0),
            DefenseRow(team="BAL", games=6, standard_pg=20.0, ppr_pg=34.0),
            DefenseRow(team="SF", games=6, standard_pg=20.0, ppr_pg=30.0),
        ]
    )

    assert "(rank 1 of 3," in _matchup_line(_matchup_context(opponent="IND", defense=defense))
    assert "(rank 1 of 3," in _matchup_line(_matchup_context(opponent="BAL", defense=defense))
    assert "(rank 3 of 3," in _matchup_line(_matchup_context(opponent="SF", defense=defense))


def test_no_matchup_line_on_bye():
    lines = _matchup_context(opponent=None)

    assert "Week 7: BYE" in lines
    assert not any(line.startswith("Matchup") or line.startswith("Points allowed") for line in lines)


def test_matchup_unavailable_when_schedule_fails():
    sched_error = SourceResult(source="schedule", status="error", as_of="Week 7", error="boom")

    context = _render([_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched_error)])

    assert "Matchup unavailable: no target-week opponent" in context.splitlines()


def test_matchup_unavailable_when_defense_empty():
    empty = SourceResult(source="defense", status="empty", as_of="Week 7")

    assert _matchup_line(_matchup_context(defense=empty)) == (
        "Matchup unavailable: no points-allowed data for WRs before Week 7"
    )


def test_matchup_unavailable_when_defense_errors():
    error = SourceResult(source="defense", status="error", as_of="Week 7", error="HTTPError: 503")

    assert _matchup_line(_matchup_context(defense=error)) == (
        "Matchup unavailable: defense failed to load: HTTPError: 503"
    )


def test_matchup_unavailable_when_opponent_missing_from_table():
    assert _matchup_line(_matchup_context(opponent="KC")) == (
        "Matchup unavailable: no games found for KC defense"
    )


def test_kicker_gets_matchup_unavailable_line():
    context = _render([_inputs(_ctx("Brandon Aubrey", "DAL", position="K"), _kicker_result())])

    lines = context.splitlines()
    assert "Matchup unavailable for kickers (kicking is not scored in the source data)" in lines
    assert not any(line.startswith("Matchup:") for line in lines)


def test_rejected_mentions_render_after_header():
    rejected = [
        RejectedMention(mention="Puka Nakua", reason="no matching player found"),
        RejectedMention(mention="Joe Nobody", reason="unknown player id"),
    ]

    lines = _render([], rejected=rejected).splitlines()

    assert lines[3:5] == [
        'Could not resolve "Puka Nakua": no matching player found',
        'Could not resolve "Joe Nobody": unknown player id',
    ]


def test_interpreted_line_when_mention_differs_from_name():
    players = [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())]

    lines = _render(players, mentions={"CeeDee Lamb": "CeeDee Lam"}).splitlines()

    header = lines.index("## CeeDee Lamb (DAL)")
    assert lines[header + 1] == 'Interpreted "CeeDee Lam" as CeeDee Lamb (DAL WR)'


def test_no_interpreted_line_when_mention_matches_after_normalizing():
    players = [_inputs(_ctx("Ja'Marr Chase", "CIN"), _ok_result())]

    context = _render(players, mentions={"Ja'Marr Chase": "  ja’marr   CHASE "})

    assert "Interpreted" not in context


def _player_lines(inputs: PlayerInputs) -> list[str]:
    return _render([inputs]).splitlines()


def test_no_roster_status_line_when_active():
    lines = _player_lines(_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result()))

    assert not any(line.startswith("Roster status") for line in lines)


def test_known_roster_status_line_follows_interpreted_line():
    players = [_inputs(_ctx("Davante Adams", "LA", roster_status="RES"), _ok_result())]

    lines = _render(players, mentions={"Davante Adams": "Davante"}).splitlines()

    header = lines.index("## Davante Adams (LA)")
    assert lines[header + 1] == 'Interpreted "Davante" as Davante Adams (LA WR)'
    assert lines[header + 2] == "Roster status: RES (reserve list, not available to play)"
    assert lines[header + 3] == "Not on the Week 7 injury report"


def test_unknown_roster_status_code():
    lines = _player_lines(_inputs(_ctx("CeeDee Lamb", "DAL", roster_status="EXE"), _ok_result()))

    assert "Roster status: EXE (unrecognized status code)" in lines


def _injury_line(injuries: SourceResult[InjuryData]) -> str:
    lines = _player_lines(_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), injuries=injuries))
    return lines[lines.index("## CeeDee Lamb (DAL)") + 1]


def test_injury_line_with_designation():
    entry = InjuryEntry(
        report_status="Questionable",
        primary_injury="Groin",
        practice_status="Limited Participation in Practice",
    )

    assert _injury_line(_injury_result(entry)) == (
        "Injury report (Week 7): Questionable (Groin). Practice: Limited Participation in Practice"
    )


def test_injury_line_listed_without_designation():
    entry = InjuryEntry(
        report_status=None, primary_injury=None, practice_status="Full Participation in Practice"
    )

    assert _injury_line(_injury_result(entry)) == (
        "Injury report (Week 7): no game designation. Practice: Full Participation in Practice"
    )


def test_injury_line_omits_null_injury_and_practice():
    entry = InjuryEntry(report_status="Out", primary_injury=None, practice_status=None)

    assert _injury_line(_injury_result(entry)) == "Injury report (Week 7): Out"


def test_injury_line_omits_null_practice_only():
    entry = InjuryEntry(report_status="Doubtful", primary_injury="Ankle", practice_status=None)

    assert _injury_line(_injury_result(entry)) == "Injury report (Week 7): Doubtful (Ankle)"


def test_injury_line_not_on_report():
    assert _injury_line(_injury_result(None)) == "Not on the Week 7 injury report"


def test_injury_line_empty():
    empty = SourceResult(source="injuries", status="empty", as_of="Week 7")

    assert _injury_line(empty) == "Week 7 injury report not available yet"


def test_injury_line_error():
    error = SourceResult(source="injuries", status="error", as_of="Week 7", error="HTTPError: 503")

    assert _injury_line(error) == "Week 7 injury report failed to load: HTTPError: 503"


def test_no_injury_line_on_bye():
    sched = _schedule_result(ScheduleWeek(week=7, opponent=None, home=None, played=False))
    empty = SourceResult(source="injuries", status="empty", as_of="Week 7")

    lines = _player_lines(_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched, injuries=empty))

    assert not any("injury report" in line.lower() for line in lines)


def _past_week_lines(*replacements: ScheduleWeek, stats=None) -> list[str]:
    sched = _schedule_result(*replacements)
    return _player_lines(_inputs(_ctx("CeeDee Lamb", "DAL"), stats or _ok_result(), sched))


def test_stats_line_home_and_away():
    lines = _past_week_lines()

    assert any(line.startswith("Week 1 vs NYG: ") for line in lines)
    assert any(line.startswith("Week 2 @ PHI: ") for line in lines)


def test_did_not_play_home_and_away():
    lines = _past_week_lines()

    assert "Week 3 vs CHI: did not play" in lines
    assert "Week 4 @ MIA: did not play" in lines


def test_stats_pending_home_and_away():
    lines = _past_week_lines(
        ScheduleWeek(week=4, opponent="MIA", home=False, played=False),
        ScheduleWeek(week=5, opponent="GB", home=True, played=False),
    )

    assert "Week 4 @ MIA: game not yet played, stats pending" in lines
    assert "Week 5 vs GB: game not yet played, stats pending" in lines


def test_stats_unavailable_home_and_away():
    error = SourceResult(source="recent_stats", status="error", as_of="Week 7", error="boom")

    lines = _past_week_lines(stats=error)

    assert "Week 3 vs CHI: stats unavailable" in lines
    assert "Week 4 @ MIA: stats unavailable" in lines


def test_stats_lines_fall_back_to_vs_when_schedule_fails():
    sched_error = SourceResult(source="schedule", status="error", as_of="Week 7", error="boom")

    lines = _player_lines(_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched_error))

    assert any(line.startswith("Week 2 vs PHI: ") for line in lines)
