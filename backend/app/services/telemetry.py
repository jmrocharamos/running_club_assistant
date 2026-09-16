"""Metadata-only Langfuse instrumentation; never export application payloads."""
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
from inspect import signature

from langfuse import Langfuse, propagate_attributes

logger = logging.getLogger(__name__)
_trace_id = ContextVar('application_trace_id', default=None)


@lru_cache(maxsize=1)
def telemetry_client():
    """Return a cached Langfuse client, or None when disabled, unconfigured, or unavailable."""
    if os.getenv('LANGFUSE_TRACING_ENABLED', 'true').lower() != 'true':
        return None
    public = os.getenv('LANGFUSE_PUBLIC_KEY')
    secret = os.getenv('LANGFUSE_SECRET_KEY')
    if not public or not secret or 'CHANGE_ME' in (public, secret):
        return None
    try:
        return Langfuse(
            public_key=public, secret_key=secret,
            base_url=os.getenv('LANGFUSE_BASE_URL') or os.getenv('LANGFUSE_HOST'),
            environment=os.getenv('ENVIRONMENT', 'development'),
            release=os.getenv('RENDER_GIT_COMMIT') or os.getenv('APP_RELEASE'),
            timeout=5,
        )
    except Exception:
        logger.warning('Langfuse initialization failed; continuing without telemetry')
        return None


def safe_update(observation, **values):
    """Apply observation metadata without letting telemetry failures interrupt the request."""
    if observation is not None:
        try:
            observation.update(**values)
        except Exception:
            logger.warning('Langfuse observation update failed')


@contextmanager
def trace_step(name, *, kind='span', metadata=None, model=None, version=None, tags=None, trace_name=None):
    """Trace a scoped operation while preserving application exceptions.

    Callers supply metadata only; error exports contain the exception class,
    without its message or traceback.
    """
    observation = manager = None
    token = None
    propagation = None
    try:
        client = telemetry_client()
        if client is not None:
            manager = client.start_as_current_observation(
                name=name, as_type=kind, metadata=metadata,
                model=model, version=version,
            )
            observation = manager.__enter__()
            token = _trace_id.set(observation.trace_id)
    except Exception:
        logger.warning('Langfuse observation creation failed')
        manager = None
    if observation is not None and ((metadata or {}).get('user_id') or tags or trace_name):
        try:
            propagation = propagate_attributes(
                user_id=(metadata or {}).get('user_id'),
                tags=list(tags) if tags else None, trace_name=trace_name,
            )
            propagation.__enter__()
        except Exception:
            propagation = None
            logger.warning('Langfuse user attribution failed')
    try:
        yield observation
    except Exception as error:
        # Never pass exception messages, tracebacks or application objects to SDK.
        safe_update(observation, level='ERROR', status_message=type(error).__name__)
        raise
    finally:
        if propagation is not None:
            try:
                propagation.__exit__(None, None, None)
            except Exception:
                logger.warning('Langfuse user attribution cleanup failed')
        if token is not None:
            _trace_id.reset(token)
        if manager is not None:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                logger.warning('Langfuse observation finalization failed')


def traced(name, *, kind='span', tags=None, workflow=False):
    """Trace a synchronous workflow using identifiers and retrieval metrics, not payloads."""
    def decorate(function):
        parameters = signature(function)
        @wraps(function)
        def wrapped(*args, **kwargs):
            bound = parameters.bind(*args, **kwargs).arguments
            user = bound.get('current_user')
            user_id = getattr(user, 'id', None) or bound.get('user_id')
            metadata = {'user_id': str(user_id)} if user_id is not None else {}
            with trace_step(name, kind=kind, metadata=metadata, tags=tags,
                            trace_name=name if workflow else None) as observation:
                result = function(*args, **kwargs)
                if kind == 'retriever' and isinstance(result, list):
                    safe_update(observation, metadata={
                        'result_count': len(result),
                        'chunk_ids': [row['chunk_id'] for row in result],
                        'distances': [row['distance'] for row in result],
                    })
                result_id = getattr(result, 'id', None)
                if result_id is not None:
                    safe_update(observation, metadata={**metadata, 'result_id': str(result_id)})
                return result
        return wrapped
    return decorate


def current_trace_id():
    """Return the active trace ID, or None when no traced operation is active."""
    return _trace_id.get()


def record_rating(recommendation):
    """Export the saved rating to its generation trace using a stable score ID."""
    if not recommendation.langfuse_trace_id:
        return
    try:
        client = telemetry_client()
        if client is not None:
            client.create_score(
                trace_id=recommendation.langfuse_trace_id,
                score_id=f'plan-rating-{recommendation.id}',
                name='plan_rating', value=recommendation.feedback_rating,
                data_type='NUMERIC',
            )
    except Exception:
        logger.warning('Langfuse rating export failed; database rating preserved')


def shutdown_telemetry():
    """Flush pending trace events without failing application shutdown."""
    try:
        client = telemetry_client()
        if client is not None:
            client.flush()
    except Exception:
        logger.warning('Langfuse flush failed during shutdown')
