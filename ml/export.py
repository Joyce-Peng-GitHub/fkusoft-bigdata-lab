"""Publish the web forecast independently of the analytics warehouse snapshot."""
import json
import os
import tempfile
from pathlib import Path


def publish_forecast(payload, destination):
    """Atomically replace the forecast so API readers never see a partial file.

    Args:
        payload: JSON-compatible history, predictions and generation metadata.
        destination: Shared JSON artifact path read by the Flask service.

    Raises:
        ValueError: A model result contains a non-finite number.
        OSError: Writing or replacing the artifact fails; the old file survives.
    """
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=destination.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(encoded)
        os.replace(temporary, destination)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
