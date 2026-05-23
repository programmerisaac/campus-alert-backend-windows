# campusalert/website/celery.py

"""
Celery application for CampusAlert.

Workers are started with:
    celery -A website worker -l info -c 4

Beat scheduler (for periodic tasks, if needed):
    celery -A website beat -l info
"""

import os
import platform
from celery import Celery



os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'website.settings')

app = Celery('campusalert')

# Use Django settings prefixed with CELERY_ for all Celery config
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all INSTALLED_APPS
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """
    Diagnostic task that prints the current request.
    Useful for verifying the Celery worker is alive and connected to the broker.
    """
    print(f'Request: {self.request!r}')


# ─── Windows: Protect the entry point ────────────────────────────────────────
# On Windows, Python uses "spawn" instead of "fork" to create new processes.
# Without this guard, importing this module in a worker subprocess re-executes
# the module-level code, which spawns another worker, which spawns another,
# causing an infinite process storm that crashes the machine.
#
# This guard is a no-op on Linux/macOS (where fork() is used and this block
# is never entered by child processes). Safe to leave in cross-platform code.
if __name__ == '__main__':
    app.start()

