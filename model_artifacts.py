"""Local model artifact boundary before deserializing a joblib file."""

import hashlib
import hmac
import json
import os
from pathlib import Path
import stat

import joblib


def load_local_model(path: Path):
    directory = path.parent
    # Resolve against the configured local model directory and reject redirections.
    if (path.anchor.startswith('\\\\') or directory.resolve() != directory.absolute()
            or path.is_symlink() or not path.is_file() or path.suffix != '.joblib'):
        raise ValueError('Untrusted model path')
    manifest_path = os.getenv('HOYA_MODEL_HASH_MANIFEST')
    with path.open('rb') as artifact:
        if not stat.S_ISREG(os.fstat(artifact.fileno()).st_mode):
            raise ValueError('Model must be a regular file')
        if manifest_path:
            hashes = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
            expected = hashes.get(f'{directory.name}/{path.name}', '')
            digest = hashlib.file_digest(artifact, 'sha256').hexdigest()
            if not isinstance(expected, str) or not hmac.compare_digest(digest, expected.lower()):
                raise ValueError('Model integrity verification failed')
            artifact.seek(0)
        return joblib.load(artifact)
