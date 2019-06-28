import django
django.setup()

from sefaria.local_settings import MULTISERVER_ENABLED

from sefaria.system.multiserver.monitor import MultiServerMonitor
from sefaria.system.scheduler.scheduler import run_background_scheduler
import logging
logger = logging.getLogger(__name__)


if __name__ == '__main__':
    if not MULTISERVER_ENABLED:
        logger.error(u"MULTISERVER_ENABLED is not set.  Exiting")
        exit()
    sched = run_background_scheduler()
    sched.print_jobs()

    monitor = MultiServerMonitor()
    monitor.listen()
