"""Cap ANTLR parser DFA recording so unique syntax cannot grow without bound.

The generated ``PlSqlParser`` keeps ``decisionsToDFA`` and
``sharedContextCache`` on the class. That is the warmup cache: the first files
fill it, later files reuse it. New lookahead paths keep adding states for the
life of the process.

This module installs a ``ParserATNSimulator`` that stops *recording* once a
state budget is reached. Hits in the existing DFA stay fast. Misses still run
ATN simulation for the current file, but are not interned, so memory stays at
the budget. ``0`` disables the cap.

Lexer DFA is left alone; it stayed an order of magnitude smaller than the
parser DFA on the synthetic corpus.
"""

from __future__ import annotations

from antlr4.atn.ParserATNSimulator import ParserATNSimulator
from antlr4.dfa.DFA import DFA
from antlr4.dfa.DFAState import DFAState

# Corpus parser DFA plateaued near 2,500 states (~300 MiB RSS). 4,096 leaves
# headroom for constructs the generator does not emit, and is still a ceiling.
DEFAULT_PARSER_DFA_MAX_STATES = 4096

_max_states = DEFAULT_PARSER_DFA_MAX_STATES


def parser_dfa_max_states() -> int:
    return _max_states


def set_parser_dfa_max_states(n: int) -> None:
    """Process-wide recording cap. ``0`` means unlimited."""
    if n < 0:
        raise ValueError(f"dfa max states must be >= 0, got {n}")
    global _max_states
    _max_states = n


def dfa_state_count(decision_to_dfa: list) -> int:
    return sum(len(dfa.states) for dfa in decision_to_dfa)


def parser_dfa_state_count() -> int:
    from PlSqlParser import PlSqlParser
    return dfa_state_count(PlSqlParser.decisionsToDFA)


def reset_parser_dfa() -> None:
    """Drop interned parser DFA states and the shared context cache.

    Tests use this so a cap measured in this process is not polluted by earlier
    parses. Production should not call it: clearing throws away warmup.
    """
    from PlSqlParser import PlSqlParser
    PlSqlParser.decisionsToDFA[:] = [
        DFA(ds, i) for i, ds in enumerate(PlSqlParser.atn.decisionToState)
    ]
    PlSqlParser.sharedContextCache.cache.clear()


class CappedParserATNSimulator(ParserATNSimulator):
    """Share the class DFA, but refuse to intern states past the budget."""

    def _at_cap(self) -> bool:
        cap = _max_states
        return cap > 0 and dfa_state_count(self.decisionToDFA) >= cap

    def addDFAState(self, dfa: DFA, D: DFAState):
        if D is self.ERROR:
            return D
        existing = dfa.states.get(D, None)
        if existing is not None:
            return existing
        if self._at_cap():
            # Do not intern, and do not run optimizeConfigs (that fills
            # sharedContextCache even when the state is discarded).
            return D
        return super().addDFAState(dfa, D)

    def addDFAEdge(self, dfa: DFA, from_: DFAState, t: int, to: DFAState):
        if to is None:
            return None
        to = self.addDFAState(dfa, to)
        if from_ is None or t < -1 or t > self.atn.maxTokenType:
            return to
        interned = to is self.ERROR or dfa.states.get(to) is to
        if not interned:
            # Pinning an ephemeral state on from_.edges would keep growing
            # memory through the interned DFA even after the cap.
            return to
        if from_.edges is None:
            from_.edges = [None] * (self.atn.maxTokenType + 2)
        from_.edges[t + 1] = to
        return to


def bind_parser(parser) -> None:
    """Replace the generated interpreter with the capped simulator."""
    parser._interp = CappedParserATNSimulator(
        parser, parser.atn, parser.decisionsToDFA, parser.sharedContextCache)
