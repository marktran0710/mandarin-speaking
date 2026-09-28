"""Which BKT parameters serve learners: the active deployment, else code defaults.

``bkt_model_active_deployment`` points at one immutable ``bkt_model_versions``
row. The database only accepts a deployment of a promotable, real-evidence
version (migration 0031). Serving reads that row through a short TTL cache; with
no deployment, or one that is not a format-aware version, the engineering
defaults in :data:`BKT_CONFIG` apply exactly as before.

Only callers that use the default ``params`` (the production recommendation
path) are switched. Any caller that passes its own ``BktConfig`` - research
treatment replays, tests, the golden verifier - keeps exactly what it passed.
"""

from __future__ import annotations

from dataclasses import asdict, replace
import logging
import os
from typing import Any

from analytics.learner_model.bkt.core import BKT_CONFIG, BktConfig
from analytics.learner_model.bkt.format_aware_fit import FORMAT_AWARE_MODEL_SCOPE, config_from_parameters
from analytics.learner_model.ttl_cache import TTLCache


logger = logging.getLogger(__name__)

# Process-local: another worker (or the promote CLI's process) sees a new
# deployment after at most this many seconds.
_active_config_cache = TTLCache(float(os.getenv("BKT_ACTIVE_CONFIG_TTL_SECONDS", "30")), max_entries=1)


def load_active_deployment(db: Any) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT deployment.model_version, deployment.updated_at, model.fit_run_id,
               model.evidence_origin, model.model_scope, model.initial_mastery,
               model.learn_rate, model.guess_rate, model.slip_rate,
               model.guess_rate_typed, model.slip_rate_typed, model.parameter_fingerprint
        FROM bkt_model_active_deployment AS deployment
        JOIN bkt_model_versions AS model ON model.version = deployment.model_version
        WHERE deployment.singleton
        """
    ).fetchone()
    return dict(row) if row else None


def config_for_version_row(row: dict[str, Any] | None) -> BktConfig:
    """Serving config for a registry row; defaults for anything not format-aware."""
    if not row:
        return BKT_CONFIG
    if row.get("model_scope") != FORMAT_AWARE_MODEL_SCOPE or row.get("guess_rate_typed") is None:
        logger.warning(
            "BKT_DEPLOYMENT_IGNORED version=%s scope=%s reason=not_format_aware",
            row.get("model_version") or row.get("version"), row.get("model_scope"),
        )
        return BKT_CONFIG
    return config_from_parameters({
        "prior": row["initial_mastery"],
        "learn": row["learn_rate"],
        "guess": row["guess_rate"],
        "slip": row["slip_rate"],
        "guess_typed": row["guess_rate_typed"],
        "slip_typed": row["slip_rate_typed"],
    })


def active_bkt_config(db: Any) -> BktConfig:
    return config_for_version_row(load_active_deployment(db))


def serving_bkt_config(db: Any, params: BktConfig) -> BktConfig:
    """Resolve the production default to the deployed parameters."""
    if params is not BKT_CONFIG:
        return params
    return _active_config_cache.get_or_compute("active", lambda: active_bkt_config(db))


def clear_active_config_cache() -> None:
    _active_config_cache.clear()


def promote_model_version(db: Any, model_version: str, reason: str) -> dict[str, Any]:
    """Point serving at ``model_version`` and rebuild every learner's cache.

    Raises ValueError for an unknown or non-format-aware version; the database
    trigger rejects any version that is not promotable real evidence.
    """
    from analytics.learner_model.bkt.mastery import rebuild_all_vocabulary_mastery

    if not reason.strip():
        raise ValueError("A deployment reason is required.")
    row = db.execute("SELECT * FROM bkt_model_versions WHERE version = %s", (model_version,)).fetchone()
    if row is None:
        raise ValueError(f"Unknown BKT model version: {model_version}")
    if row.get("model_scope") != FORMAT_AWARE_MODEL_SCOPE or row.get("guess_rate_typed") is None:
        raise ValueError(f"{model_version} is not a format-aware model and cannot serve learners.")
    previous = load_active_deployment(db)
    db.execute(
        """
        INSERT INTO bkt_model_active_deployment (singleton, model_version, updated_at)
        VALUES (TRUE, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (singleton) DO UPDATE
            SET model_version = EXCLUDED.model_version, updated_at = EXCLUDED.updated_at
        """,
        (model_version,),
    )
    db.execute(
        "INSERT INTO bkt_model_deployment_events (model_version, previous_model_version, reason) VALUES (%s, %s, %s)",
        (model_version, previous["model_version"] if previous else None, reason.strip()),
    )
    config = config_for_version_row(dict(row))
    rebuild_all_vocabulary_mastery(db, config)
    clear_active_config_cache()
    return {
        "modelVersion": model_version,
        "previousModelVersion": previous["model_version"] if previous else None,
        "parameters": asdict(config),
    }


def deactivate_deployment(db: Any) -> dict[str, Any]:
    """Return serving to the code defaults and rebuild every learner's cache."""
    from analytics.learner_model.bkt.mastery import rebuild_all_vocabulary_mastery

    previous = load_active_deployment(db)
    db.execute("DELETE FROM bkt_model_active_deployment")
    clear_active_config_cache()
    # A copy, not BKT_CONFIG itself: the defaults must be used as given rather
    # than re-resolved through the (just cleared) deployment lookup.
    rebuild_all_vocabulary_mastery(db, replace(BKT_CONFIG))
    clear_active_config_cache()
    return {"previousModelVersion": previous["model_version"] if previous else None}
