"""Mutual exclusion for supported local research/participant servers."""
import json
from urllib.error import URLError
from urllib.request import urlopen


def require_peer_closed(port, mode):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
            peer = json.loads(response.read(4096))
    except (OSError, URLError, ValueError):
        return
    if peer.get('local_only') and peer.get('mode') == mode:
        raise RuntimeError(f'Encerre o servidor Anya {mode} na porta {port} antes de iniciar este modo.')


from contextlib import contextmanager
import os


@contextmanager
def exclusive_server(root, peer_port, peer_mode):
    """An OS-held advisory lock also closes simultaneous-start races."""
    lock = (root / '.server-mode.lock').open('a+b')
    acquired = False
    try:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            raise RuntimeError('Outro servidor Anya já usa esta pasta de dados. Encerre-o antes da coleta.') from None
        require_peer_closed(peer_port, peer_mode)
        yield
    finally:
        if acquired:
            lock.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
