import ffassistant.answer as answer_module
from ffassistant.answer import PlayerInputs, answer, render_context
from ffassistant.clients.anthropic_client import GeneratedAnswer
from ffassistant.contracts import Answer, ParsedRequest, ResolvedContext, SourceResult
from ffassistant.sources.recent_stats import GameLine, RecentStatsData
from ffassistant.sources.schedule import ScheduleData, ScheduleWeek


def _parsed() -> ParsedRequest:
    return ParsedRequest(
        raw_prompt="Lamb or Jefferson?",
        player_names=["CeeDee Lamb", "Justin Jefferson"],
        week=7,
        scoring_format="PPR",
    )


def _ctx(name: str, team: str, scoring_format: str = "PPR") -> ResolvedContext:
    return ResolvedContext(
        player_id="00-0000001",
        player_name=name,
        team=team,
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


def _inputs(
    ctx: ResolvedContext,
    stats: SourceResult[RecentStatsData],
    sched: SourceResult[ScheduleData] | None = None,
) -> PlayerInputs:
    return PlayerInputs(
        ctx=ctx, recent_stats=stats, schedule=sched if sched is not None else _schedule_result()
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
    context = render_context(_parsed(), [])

    assert "Lamb or Jefferson?" in context
    assert "7" in _line_with(context, "Week")
    assert "PPR" in _line_with(context, "Scoring format")


def test_render_context_ok_renders_one_row_per_game():
    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    week_1 = _line_with(context, "NYG")
    week_2 = _line_with(context, "PHI")
    assert "DAL" in _line_with(context, "CeeDee Lamb")
    assert "Week 1" in week_1 and "receptions=6" in week_1
    assert "fantasy_points (PPR)=18.4" in week_1
    assert "Week 2" in week_2 and "receptions=4" in week_2


def test_render_context_uses_standard_points_for_standard_scoring():
    context = render_context(
        _parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL", "Standard"), _ok_result())]
    )

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Standard)=12.4" in week_1
    assert "18.4" not in week_1


def test_render_context_derives_half_ppr_points():
    context = render_context(
        _parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL", "Half-PPR"), _ok_result())]
    )

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Half-PPR)=15.4" in week_1
    assert "12.4" not in week_1 and "18.4" not in week_1


def test_render_context_shows_both_labeled_for_unknown_format():
    context = render_context(
        _parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL", "Six-Point Passing TD"), _ok_result())]
    )

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Standard)=12.4" in week_1
    assert "fantasy_points (PPR)=18.4" in week_1


def test_render_context_empty_without_schedule_says_no_games():
    empty = SourceResult(source="recent_stats", status="empty", as_of="Week 7")
    no_schedule = SourceResult(source="schedule", status="empty", as_of="Week 7")

    context = render_context(
        _parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), empty, no_schedule)]
    )

    line = _line_with(context.lower(), "no games")
    assert "DAL" in _line_with(context, "CeeDee Lamb")
    assert "week 7" in line


def test_render_context_error_includes_error_string():
    error = SourceResult(
        source="recent_stats", status="error", as_of="Week 7", error="HTTPError: 503"
    )

    context = render_context(_parsed(), [_inputs(_ctx("Justin Jefferson", "MIN"), error)])

    assert "MIN" in _line_with(context, "Justin Jefferson")
    assert "HTTPError: 503" in context


def test_render_context_keeps_every_player():
    empty = SourceResult(source="recent_stats", status="empty", as_of="Week 7")
    error = SourceResult(source="recent_stats", status="error", as_of="Week 7", error="boom")

    context = render_context(
        _parsed(),
        [
            _inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result()),
            _inputs(_ctx("Justin Jefferson", "MIN"), empty),
            _inputs(_ctx("Ja'Marr Chase", "CIN"), error),
        ],
    )

    for name, team in [("CeeDee Lamb", "DAL"), ("Justin Jefferson", "MIN"), ("Ja'Marr Chase", "CIN")]:
        assert team in _line_with(context, name)


def test_answer_builds_answer_from_generated_output(monkeypatch):
    seen_contexts = []

    def fake_generate_answer(context):
        seen_contexts.append(context)
        return GeneratedAnswer(answer="Start **Lamb**.", cited_doc_ids=[])

    monkeypatch.setattr(answer_module, "generate_answer", fake_generate_answer)
    players = [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())]

    result = answer(_parsed(), players)

    assert result == Answer(answer="Start **Lamb**.", cited_doc_ids=[])
    assert seen_contexts == [render_context(_parsed(), players)]


def test_target_week_home_game():
    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    assert "Week 7: vs IND" in context.splitlines()


def test_target_week_away_game():
    sched = _schedule_result(ScheduleWeek(week=7, opponent="BAL", home=False, played=False))

    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched)])

    assert "Week 7: @ BAL" in context.splitlines()


def test_target_week_bye():
    sched = _schedule_result(ScheduleWeek(week=7, opponent=None, home=None, played=False))

    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched)])

    assert "Week 7: BYE" in context.splitlines()


def test_target_week_line_follows_header():
    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    lines = context.splitlines()
    header = lines.index("## CeeDee Lamb (DAL)")
    assert lines[header + 1] == "Week 7: vs IND"


def test_past_bye_week_line():
    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    assert "Week 6: BYE" in context.splitlines()


def test_played_week_without_stat_row_is_did_not_play():
    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    assert "Week 4 vs MIA: did not play" in context.splitlines()


def test_unplayed_past_week_is_stats_pending():
    sched = _schedule_result(ScheduleWeek(week=6, opponent="SF", home=True, played=False))

    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched)])

    assert "Week 6 vs SF: game not yet played, stats pending" in context.splitlines()


def test_one_line_per_past_week_in_order():
    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    week_lines = [line for line in context.splitlines() if line.startswith("Week ") and ":" in line]
    assert [line.split(":")[0].split()[1] for line in week_lines] == ["7", "1", "2", "3", "4", "5", "6"]


def test_stats_error_with_schedule_keeps_schedule_lines():
    error = SourceResult(
        source="recent_stats", status="error", as_of="Week 7", error="HTTPError: 503"
    )

    context = render_context(_parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), error)])

    lines = context.splitlines()
    assert "recent_stats failed to load: HTTPError: 503" in lines
    assert "Week 6: BYE" in lines
    assert "Week 4 vs MIA: stats unavailable" in lines
    assert not any("did not play" in line for line in lines)


def test_schedule_error_falls_back_to_stats_only():
    sched_error = SourceResult(
        source="schedule", status="error", as_of="Week 7", error="HTTPError: 502"
    )

    context = render_context(
        _parsed(), [_inputs(_ctx("CeeDee Lamb", "DAL"), _ok_result(), sched_error)]
    )

    lines = context.splitlines()
    assert "HTTPError: 502" in _line_with(context, "schedule")
    assert "fantasy_points (PPR)=18.4" in _line_with(context, "NYG")
    assert "receptions=4" in _line_with(context, "PHI")
    assert not any("BYE" in line or "did not play" in line for line in lines)


def test_kicker_renders_raw_stats_without_points():
    context = render_context(_parsed(), [_inputs(_ctx("Brandon Aubrey", "DAL"), _kicker_result())])

    week_1 = _line_with(context, "NYG")
    assert "fg_made=3" in week_1 and "fg_att=4" in week_1 and "pat_made=2" in week_1
    assert "fantasy_points" not in week_1
    assert (
        "fantasy points unavailable for kickers (kicking is not scored in the source data)"
        in context.splitlines()
    )
