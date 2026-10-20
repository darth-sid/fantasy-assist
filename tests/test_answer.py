import answer as answer_module
from answer import answer, render_context
from clients.anthropic_client import GeneratedAnswer
from contracts import Answer, ParsedRequest, ResolvedContext, SourceResult
from sources.recent_stats import GameLine, RecentStatsData


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
    context = render_context(_parsed(), [(_ctx("CeeDee Lamb", "DAL"), _ok_result())])

    week_1 = _line_with(context, "NYG")
    week_2 = _line_with(context, "PHI")
    assert "DAL" in _line_with(context, "CeeDee Lamb")
    assert "Week 1" in week_1 and "receptions=6" in week_1
    assert "fantasy_points (PPR)=18.4" in week_1
    assert "Week 2" in week_2 and "receptions=4" in week_2


def test_render_context_uses_standard_points_for_standard_scoring():
    context = render_context(
        _parsed(), [(_ctx("CeeDee Lamb", "DAL", "Standard"), _ok_result())]
    )

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Standard)=12.4" in week_1
    assert "18.4" not in week_1


def test_render_context_derives_half_ppr_points():
    context = render_context(
        _parsed(), [(_ctx("CeeDee Lamb", "DAL", "Half-PPR"), _ok_result())]
    )

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Half-PPR)=15.4" in week_1
    assert "12.4" not in week_1 and "18.4" not in week_1


def test_render_context_shows_both_labeled_for_unknown_format():
    context = render_context(
        _parsed(), [(_ctx("CeeDee Lamb", "DAL", "Six-Point Passing TD"), _ok_result())]
    )

    week_1 = _line_with(context, "NYG")
    assert "fantasy_points (Standard)=12.4" in week_1
    assert "fantasy_points (PPR)=18.4" in week_1


def test_render_context_empty_says_no_games():
    empty = SourceResult(source="recent_stats", status="empty", as_of="Week 7")

    context = render_context(_parsed(), [(_ctx("CeeDee Lamb", "DAL"), empty)])

    line = _line_with(context.lower(), "no games")
    assert "DAL" in _line_with(context, "CeeDee Lamb")
    assert "week 7" in line


def test_render_context_error_includes_error_string():
    error = SourceResult(
        source="recent_stats", status="error", as_of="Week 7", error="HTTPError: 503"
    )

    context = render_context(_parsed(), [(_ctx("Justin Jefferson", "MIN"), error)])

    assert "MIN" in _line_with(context, "Justin Jefferson")
    assert "HTTPError: 503" in context


def test_render_context_keeps_every_player():
    empty = SourceResult(source="recent_stats", status="empty", as_of="Week 7")
    error = SourceResult(source="recent_stats", status="error", as_of="Week 7", error="boom")

    context = render_context(
        _parsed(),
        [
            (_ctx("CeeDee Lamb", "DAL"), _ok_result()),
            (_ctx("Justin Jefferson", "MIN"), empty),
            (_ctx("Ja'Marr Chase", "CIN"), error),
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
    players = [(_ctx("CeeDee Lamb", "DAL"), _ok_result())]

    result = answer(_parsed(), players)

    assert result == Answer(answer="Start **Lamb**.", cited_doc_ids=[])
    assert seen_contexts == [render_context(_parsed(), players)]
