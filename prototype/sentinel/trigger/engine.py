"""
Two-stage trigger: a cheap lexical prefilter, then semantic confirmation.

SPEC §8. The two-stage structure is itself the answer to "isn't this just
keyword matching?" -- so it is worth being precise about what each stage does.

STAGE 1 is a keyword pass. It is fast, it runs on every utterance, and on its
own it is exactly the naive thing critics have in mind. It fires on "I'll
transfer you to the other line" and it misses "push the funds across tonight".

STAGE 2 embeds the utterance with MiniLM. The obvious design -- cosine
similarity against the canonical intent sentences, fire above a threshold --
DOES NOT WORK, and it is worth being precise about why, because the failure is
instructive. Measured on this intent set:

    high-risk paraphrases   0.44 - 0.65
    ordinary banking talk   0.25 - 0.61

The ranges overlap, so no threshold exists. "Please visit the branch at your
convenience with the documents" scores 0.61; "push the funds across tonight"
scores 0.44. A general-purpose sentence encoder measures topical relatedness,
and everything said on a banking call is topically related to banking.

So stage 2 asks a comparative question instead of an absolute one:

    margin = similarity(utterance, nearest fraud intent)
           - similarity(utterance, nearest benign anchor)

Is this closer to a fraud instruction than to normal call content? That IS
separable -- on the curated set all 15 positives clear +0.28 and all 15
negatives sit below -0.01. It is a two-class nearest-neighbour decision rather
than a threshold, and BENIGN_ANCHORS in intents.py is the second class.

The two stages then combine as:

    margin >= semantic_margin                    -> fire (catches paraphrases)
    lexical hit AND margin >= lexical_confirm_floor -> fire (catches the obvious)
    lexical hit AND margin below that floor      -> stay quiet

That last line is where "I'll transfer you to the other line" dies: stage 1 hits
it on the word "transfer", and its margin of -0.10 says it is closer to normal
call content than to fraud. A keyword matcher fires; this does not.

Known limits are measured and written down in intents.py: KNOWN_MISSES and
KNOWN_FALSE_POSITIVES, both asserted in test_trigger.py.
"""
from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Sequence, Tuple

import numpy as np

from sentinel.config import ModelConfig, TriggerConfig
from sentinel.trigger.intents import (
    INTENTS,
    LABELS,
    benign_sentences,
    canonical_sentences,
)
from sentinel.types import TriggerEvent, Utterance


def _term_pattern(term: str) -> "re.Pattern":
    """Word-boundary match, so 'pin' does not fire on 'shipping'."""
    return re.compile(r"(?<!\w)" + re.escape(term).replace(r"\ ", r"\s+") + r"(?!\w)",
                      re.IGNORECASE)


_PATTERNS = {
    intent.key: [(term, _term_pattern(term)) for term in intent.terms]
    for intent in INTENTS
}


def lexical_hits(text: str) -> List[Tuple[str, str]]:
    """[(intent_key, matched_term)] for every term present. Stage 1."""
    hits: List[Tuple[str, str]] = []
    for key, patterns in _PATTERNS.items():
        for term, pattern in patterns:
            if pattern.search(text):
                hits.append((key, term))
    return hits


class Match(NamedTuple):
    intent_key: str
    intent_similarity: float
    benign_similarity: float
    matched_sentence: str

    @property
    def margin(self) -> float:
        """The number the decision is actually made on."""
        return self.intent_similarity - self.benign_similarity


class SemanticMatcher:
    """
    Stage 2. MiniLM embeddings, scored as fraud-intent similarity MINUS
    benign-anchor similarity.

    Loaded once and reused; encoding one utterance is ~10 ms, which is why this
    can sit in the pipeline thread rather than needing a worker of its own.
    """

    def __init__(self, cfg: ModelConfig) -> None:
        from sentence_transformers import SentenceTransformer

        from sentinel.config import prefer_local_model_cache

        prefer_local_model_cache()
        self.model_id = cfg.trigger_encoder_id
        self._model = SentenceTransformer(cfg.trigger_encoder_id, cache_folder=cfg.hf_cache())
        sentences, keys = canonical_sentences()
        self._keys = keys
        self._sentences = sentences
        self._intents = self._encode(sentences)
        self._benign = self._encode(benign_sentences())

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(list(texts), convert_to_numpy=True,
                                     normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)

    def best_match(self, text: str) -> Match:
        vector = self._encode([text])[0]
        sims = self._intents @ vector  # both normalised, so this is cosine
        idx = int(np.argmax(sims))
        return Match(
            intent_key=self._keys[idx],
            intent_similarity=float(sims[idx]),
            benign_similarity=float(np.max(self._benign @ vector)),
            matched_sentence=self._sentences[idx],
        )


class TriggerEngine:
    """Runs both stages and produces TriggerEvents."""

    def __init__(
        self,
        trigger_cfg: TriggerConfig,
        model_cfg: ModelConfig,
        matcher: Optional[SemanticMatcher] = None,
    ) -> None:
        self.cfg = trigger_cfg
        self.matcher = matcher if matcher is not None else SemanticMatcher(model_cfg)

    def evaluate(self, utterance: Utterance) -> Optional[TriggerEvent]:
        text = (utterance.text or "").strip()
        if not text:
            return None

        # Very short utterances carry too little for either stage to judge.
        # "transfer" on its own is a word, not an instruction.
        if len(text.split()) < self.cfg.min_words:
            return None

        hits = lexical_hits(text)
        match = self.matcher.best_match(text)
        margin = match.margin

        fired_semantic = margin >= self.cfg.semantic_margin
        fired_lexical = bool(hits) and margin >= self.cfg.lexical_confirm_floor

        if not (fired_semantic or fired_lexical):
            return None

        if fired_semantic and hits:
            stage = "both"
        elif fired_semantic:
            stage = "semantic"
        else:
            stage = "lexical"

        # Prefer the intent stage 1 agreed on, so the reported family matches
        # the words a listener actually heard.
        intent_key = match.intent_key
        hit_keys = [k for k, _ in hits]
        if stage == "lexical" and hit_keys:
            intent_key = hit_keys[0]

        return TriggerEvent(
            t_ms=utterance.t_end_ms,
            utterance=utterance,
            intent=LABELS.get(intent_key, intent_key),
            similarity=match.intent_similarity,
            margin=margin,
            stage=stage,
            matched_terms=tuple(sorted({term for k, term in hits if k == intent_key})),
        )

    def describe(self, event: TriggerEvent) -> str:
        """The sentence that goes at the top of the evidence panel."""
        how = {
            "semantic": "matched by meaning, not keywords",
            "lexical": "matched on wording, confirmed by meaning",
            "both": "matched on both wording and meaning",
        }[event.stage]
        return (
            f'TRIGGER — {event.intent} ({how}; closer to a fraud instruction '
            f'than to normal call content by {event.margin:+.2f}): '
            f'"{event.utterance.text.strip()}"'
        )


class ScriptedOverlay:
    """
    Injects the demo's scripted transcript lines at their configured times.

    IMPLEMENTATION-PLAN 2.6: ASVspoof clips are read speech and contain no
    financial instruction, so the trigger would never fire on them naturally.
    The overlay makes the trigger MECHANISM demonstrable on audio that is not a
    fraud call.

    Every line it produces has scripted=True, and that flag is carried to the UI
    and rendered with a visible marker. An unlabelled scripted line would make
    the whole demo dishonest, so the flag is set here and never cleared.

    The same overlay is applied to both demo calls, deliberately. If the trigger
    only ever fired on the attack call, the demo would be rigged and a judge
    would be right to ask how the trigger "knew". Both calls trigger; what
    differs is what verification finds afterwards.
    """

    def __init__(self, utterances: Sequence) -> None:
        self._pending = sorted(
            (
                Utterance(
                    text=u.text,
                    t_start_ms=max(0, u.t_ms - 2000),
                    t_end_ms=u.t_ms,
                    scripted=True,
                )
                for u in utterances
            ),
            key=lambda u: u.t_end_ms,
        )
        self._index = 0

    @property
    def enabled(self) -> bool:
        return bool(self._pending)

    def due(self, t_ms: int) -> List[Utterance]:
        """Overlay lines whose time has arrived. Each is returned exactly once."""
        out: List[Utterance] = []
        while self._index < len(self._pending) and self._pending[self._index].t_end_ms <= t_ms:
            out.append(self._pending[self._index])
            self._index += 1
        return out

    def reset(self) -> None:
        self._index = 0
