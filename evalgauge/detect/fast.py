"""Tier 1 — the fast, cheap, surface-level classifier.

TF-IDF features + logistic regression. The defining property is that TF-IDF is a
*surface* representation: it sees which tokens appear, not what they mean. So the fast
tier recognizes the visible tells of Group I families (role-play, prefix-injection) and
is structurally blind to Group II families that *disguise* (encoding) or *distribute*
(many-shot, gradual escalation) their signal. See docs/threat_model.md §3.

In production you'd replace TF-IDF with neural embeddings. The pipeline is identical —
and so is the shape of the blind spot: no surface featurizer can recover intent that has
been encoded away. Closing that gap is exactly why the judge tier (Tier 2) exists.

Training happens offline on *labeled* data. At inference the classifier sees only text
(an Event's text) and emits a score in [0, 1]. It never touches a label — that is the
detector's blindness (stream/event.py), preserved here.
"""

from __future__ import annotations

from collections.abc import Iterable

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ..generate.schema import Label, LabeledPrompt


class FastClassifier:
    """A trainable surface-level jailbreak scorer.

    min_df=2 drops tokens seen only once — which quietly guarantees a one-off base64
    blob (unique per prompt) never becomes a feature. That is realistic: a surface model
    can't memorize every possible ciphertext, so encoding attacks that hide their payload
    fall outside its vocabulary by construction.
    """

    def __init__(self, *, ngram_range: tuple[int, int] = (1, 2), min_df: int = 2) -> None:
        self.vectorizer = TfidfVectorizer(
            ngram_range=ngram_range, min_df=min_df, lowercase=True
        )
        # class_weight balances the training mix (attacks outnumber benign in our
        # stratified corpus) so the model doesn't just learn "guess attack".
        self.model = LogisticRegression(max_iter=1000, class_weight="balanced")
        self._fitted = False

    def fit(self, prompts: Iterable[LabeledPrompt]) -> "FastClassifier":
        prompts = list(prompts)
        texts = [p.text for p in prompts]
        y = [1 if p.label is Label.ATTACK else 0 for p in prompts]
        X = self.vectorizer.fit_transform(texts)
        self.model.fit(X, y)
        self._fitted = True
        return self

    def score(self, text: str) -> float:
        """Probability in [0, 1] that `text` is an attack. The cheap tier-1 signal."""
        if not self._fitted:
            raise RuntimeError("FastClassifier.score called before fit()")
        X = self.vectorizer.transform([text])
        return float(self.model.predict_proba(X)[0, 1])
